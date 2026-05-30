#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════╗
║         RAFT SURVIVORS — Game Server             ║
║  Run on your Droplet:  python server.py          ║
╚══════════════════════════════════════════════════╝
"""

import asyncio, json, math, random, time, uuid, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import websockets
from shared.constants import *

# ─────────────────────── Utilities ───────────────────────

def dist(a, b):
    return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def rand_id(n=6):
    return ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=n))

# ─────────────────────── Tile Map ────────────────────────

def generate_world(seed=None):
    if seed: random.seed(seed)
    tiles = [[T_WATER]*WORLD_H for _ in range(WORLD_W)]
    cx, cy = WORLD_W//2, WORLD_H//2

    # Starting raft (9x7 platform)
    for x in range(cx-4, cx+5):
        for y in range(cy-3, cy+4):
            tiles[x][y] = T_RAFT

    # Random islands
    islands = []
    for _ in range(6):
        for attempt in range(30):
            ix = random.randint(8, WORLD_W-8)
            iy = random.randint(8, WORLD_H-8)
            if dist((ix,iy),(cx,cy)) < 18:
                continue
            too_close = any(dist((ix,iy),i) < 10 for i in islands)
            if too_close: continue
            islands.append((ix,iy))
            r = random.randint(3, 6)
            for dx in range(-r, r+1):
                for dy in range(-r, r+1):
                    if dx*dx+dy*dy <= r*r+r:
                        nx,ny = ix+dx, iy+dy
                        if 0<=nx<WORLD_W and 0<=ny<WORLD_H:
                            tiles[nx][ny] = T_SAND if dx*dx+dy*dy > (r-1)**2 else T_ISLAND
            # Trees & rocks
            for _ in range(r*2):
                tx = ix + random.randint(-r+1, r-1)
                ty = iy + random.randint(-r+1, r-1)
                if 0<=tx<WORLD_W and 0<=ty<WORLD_H and tiles[tx][ty]==T_ISLAND:
                    tiles[tx][ty] = random.choice([T_TREE, T_ROCK])
            break

    # Beacon in raft center
    tiles[cx][cy] = T_FIRE
    return tiles, (cx, cy), islands

# ─────────────────────── Entities ────────────────────────

class Player:
    def __init__(self, pid, name, spawn):
        self.id = pid
        self.name = name
        self.x, self.y = float(spawn[0]), float(spawn[1])
        self.hp = PLAYER_MAX_HP
        self.hunger = PLAYER_MAX_HUNGER
        self.inventory = {"wood":0,"stone":0,"rope":0,"fuel":0,"plank":0,"food":0,"torch":0,"wall":0}
        self.input = {"dx":0,"dy":0}
        self.alive = True
        self.safe  = True
        self.ws    = None
        self.last_attack = 0.0

    def to_dict(self):
        return {
            "id":self.id, "name":self.name,
            "x":round(self.x,2),"y":round(self.y,2),
            "hp":self.hp,"hunger":round(self.hunger,1),
            "alive":self.alive,"safe":self.safe,
            "inv":self.inventory
        }

class Monster:
    def __init__(self, kind, x, y):
        self.id   = str(uuid.uuid4())[:8]
        self.kind = kind
        self.x, self.y = float(x), float(y)
        spec = MONSTER_TYPES[kind]
        self.hp    = spec["hp"]
        self.max_hp= spec["hp"]
        self.dmg   = spec["dmg"]
        self.speed = spec["speed"]
        self.range = spec["range"]
        self.xp    = spec["xp"]
        self.target_id = None
        self.alive = True
        self.last_atk = 0.0

    def to_dict(self):
        return {
            "id":self.id,"kind":self.kind,
            "x":round(self.x,2),"y":round(self.y,2),
            "hp":self.hp,"max_hp":self.max_hp
        }

# ─────────────────────── Lobby / Game ────────────────────

class GameLobby:
    def __init__(self, lobby_id, host_name, seed=None):
        self.id      = lobby_id
        self.host    = host_name
        self.seed    = seed or random.randint(0,999999)
        self.players : dict[str, Player] = {}
        self.monsters: dict[str, Monster] = {}
        self.tiles, self.beacon_pos, self.islands = generate_world(self.seed)
        self.beacon_fuel = BEACON_MAX_FUEL
        self.day_time    = 0.0          # seconds since current phase start
        self.is_night    = False
        self.night_count = 0
        self.loot_chests : list[dict] = []
        self.running     = True
        self._last_tick  = time.time()
        self.chat_log    : list[dict] = []
        self._spawn_timer= 0.0
        self._warn_sent  = False

        # Scatter some starter loot on islands
        self._place_chests()

    def _place_chests(self):
        for (ix,iy) in self.islands:
            loot = {"wood": random.randint(3,8), "stone": random.randint(1,4)}
            if random.random() > 0.5: loot["fuel"] = random.randint(1,3)
            if random.random() > 0.7: loot["rope"] = random.randint(1,2)
            self.loot_chests.append({"x":ix,"y":iy,"items":loot,"id":rand_id(4)})

    def spawn_pos(self):
        return (self.beacon_pos[0]+random.uniform(-1,1),
                self.beacon_pos[1]+random.uniform(-1,1))

    def add_player(self, pid, name):
        p = Player(pid, name, self.spawn_pos())
        p.inventory["wood"] = 5
        p.inventory["stone"]= 3
        self.players[pid] = p
        return p

    def remove_player(self, pid):
        self.players.pop(pid, None)

    # ── Physics / AI tick ──────────────────────────────

    async def tick(self):
        now  = time.time()
        dt   = now - self._last_tick
        self._last_tick = now
        if dt > 0.2: dt = 0.2        # clamp spike

        self._update_time(dt)
        self._update_players(dt)
        self._update_monsters(dt)
        await self._broadcast_state()

    def _update_time(self, dt):
        self.day_time += dt
        phase_dur = NIGHT_DURATION if self.is_night else DAY_DURATION
        if self.day_time >= phase_dur:
            self.day_time -= phase_dur
            self.is_night = not self.is_night
            self._warn_sent = False
            if self.is_night:
                self.night_count += 1
                self._spawn_monsters()

        if self.is_night:
            drain = BEACON_DRAIN * dt
            self.beacon_fuel = max(0, self.beacon_fuel - drain)
        else:
            # Warn 10s before night
            remaining = DAY_DURATION - self.day_time
            if not self._warn_sent and remaining <= 10:
                self._warn_sent = True
                asyncio.ensure_future(self._broadcast_raw({"type":MSG["NIGHT_WARN"],"secs":int(remaining)}))

    def _beacon_on(self):
        return self.beacon_fuel > 0

    def _update_players(self, dt):
        for p in self.players.values():
            if not p.alive: continue

            # Movement
            inp = p.input
            dx, dy = inp.get("dx",0), inp.get("dy",0)
            mag = math.sqrt(dx*dx+dy*dy)
            if mag > 0:
                dx, dy = dx/mag, dy/mag
            p.x = clamp(p.x + dx*PLAYER_SPEED*dt, 0, WORLD_W-1)
            p.y = clamp(p.y + dy*PLAYER_SPEED*dt, 0, WORLD_H-1)

            # Hunger
            p.hunger = max(0, p.hunger - HUNGER_DRAIN*dt)
            if p.hunger == 0:
                p.hp -= 2*dt
                if p.hp <= 0: p.alive = False

            # Safe zone check
            if self._beacon_on():
                d = dist((p.x,p.y), self.beacon_pos)
                p.safe = d <= BEACON_RADIUS
            else:
                p.safe = False

            # Loot pickup
            for chest in self.loot_chests[:]:
                if dist((p.x,p.y),(chest["x"],chest["y"])) < 1.2:
                    for item,qty in chest["items"].items():
                        p.inventory[item] = p.inventory.get(item,0)+qty
                    self.loot_chests.remove(chest)
                    asyncio.ensure_future(self._send_player(p.id,{
                        "type":MSG["LOOT"],"items":chest["items"]
                    }))

    def _update_monsters(self, dt):
        if not self.is_night:
            self.monsters.clear()
            return

        now = time.time()
        alive_players = [p for p in self.players.values() if p.alive]
        if not alive_players: return

        for m in list(self.monsters.values()):
            if not m.alive:
                del self.monsters[m.id]
                continue

            # AI: chase nearest player not in safe zone
            targets = [p for p in alive_players if not p.safe or not self._beacon_on()]
            if not targets:
                targets = alive_players  # if beacon off, chase everyone

            nearest = min(targets, key=lambda p: dist((m.x,m.y),(p.x,p.y)), default=None)
            if not nearest: continue

            d = dist((m.x,m.y),(nearest.x,nearest.y))
            if d > 0.1:
                m.x += (nearest.x-m.x)/d * m.speed * dt
                m.y += (nearest.y-m.y)/d * m.speed * dt

            # Attack
            if d < m.range and now - m.last_atk > 1.0:
                m.last_atk = now
                nearest.hp -= m.dmg
                if nearest.hp <= 0:
                    nearest.alive = False
                    asyncio.ensure_future(self._send_player(nearest.id, {"type":MSG["DEATH"]}))

    def _spawn_monsters(self):
        count = 3 + self.night_count * 2
        bx, by = self.beacon_pos
        for _ in range(count):
            angle = random.uniform(0, 2*math.pi)
            r     = random.uniform(BEACON_RADIUS+2, BEACON_RADIUS+8)
            mx = clamp(bx + math.cos(angle)*r, 0, WORLD_W-1)
            my = clamp(by + math.sin(angle)*r, 0, WORLD_H-1)
            kind  = random.choices(
                list(MONSTER_TYPES.keys()),
                weights=[5,2,3]
            )[0]
            m = Monster(kind, mx, my)
            self.monsters[m.id] = m

    # ── Crafting / Fueling ─────────────────────────────

    def craft(self, pid, item):
        p = self.players.get(pid)
        if not p or not p.alive: return "dead"
        recipe = RECIPES.get(item)
        if not recipe: return "unknown_recipe"
        for ing, qty in recipe.items():
            if p.inventory.get(ing,0) < qty:
                return "no_materials"
        for ing, qty in recipe.items():
            p.inventory[ing] -= qty
        p.inventory[item] = p.inventory.get(item,0)+1
        return "ok"

    def add_fuel(self, pid, qty):
        p = self.players.get(pid)
        if not p: return "no_player"
        have = p.inventory.get("fuel",0)
        give = min(qty, have, BEACON_MAX_FUEL-self.beacon_fuel)
        if give <= 0: return "no_fuel"
        p.inventory["fuel"] -= int(give)
        self.beacon_fuel = min(BEACON_MAX_FUEL, self.beacon_fuel+give)
        return "ok"

    def player_attack(self, pid):
        p = self.players.get(pid)
        if not p or not p.alive: return
        now = time.time()
        if now - p.last_attack < 0.5: return
        p.last_attack = now
        for m in self.monsters.values():
            if not m.alive: continue
            if dist((p.x,p.y),(m.x,m.y)) < 1.5:
                m.hp -= 25
                if m.hp <= 0:
                    m.alive = False

    def place_tile(self, pid, tx, ty, tile_type):
        p = self.players.get(pid)
        if not p: return "no_player"
        if dist((p.x,p.y),(tx,ty)) > 3: return "too_far"
        cost = {}
        if tile_type == T_RAFT:  cost = {"plank":1}
        elif tile_type == T_WALL: cost = {"wall":1}
        elif tile_type == T_TORCH: cost = {"torch":1}
        for ing,qty in cost.items():
            if p.inventory.get(ing,0) < qty: return "no_materials"
        for ing,qty in cost.items():
            p.inventory[ing] -= qty
        if 0<=tx<WORLD_W and 0<=ty<WORLD_H:
            self.tiles[tx][ty] = tile_type
        return "ok"

    # ── Network helpers ────────────────────────────────

    def state_snapshot(self):
        phase_dur = NIGHT_DURATION if self.is_night else DAY_DURATION
        remaining = phase_dur - self.day_time
        return {
            "type": MSG["STATE"],
            "players":  [p.to_dict() for p in self.players.values()],
            "monsters": [m.to_dict() for m in self.monsters.values() if m.alive],
            "beacon_fuel": round(self.beacon_fuel,1),
            "is_night":   self.is_night,
            "night_count":self.night_count,
            "phase_remaining": round(remaining,1),
            "chests": [{"id":c["id"],"x":c["x"],"y":c["y"]} for c in self.loot_chests],
        }

    def world_snapshot(self):
        flat = []
        for col in self.tiles:
            flat.extend(col)
        return {
            "type":   MSG["WORLD"],
            "w":      WORLD_W,
            "h":      WORLD_H,
            "tiles":  flat,
            "beacon": list(self.beacon_pos),
            "seed":   self.seed,
        }

    async def _send_player(self, pid, msg):
        p = self.players.get(pid)
        if p and p.ws:
            try:
                await p.ws.send(json.dumps(msg))
            except: pass

    async def _broadcast_raw(self, msg):
        data = json.dumps(msg)
        for p in list(self.players.values()):
            if p.ws:
                try: await p.ws.send(data)
                except: pass

    async def _broadcast_state(self):
        snap = self.state_snapshot()
        await self._broadcast_raw(snap)

    async def broadcast_chat(self, sender, text):
        msg = {"type":MSG["CHAT_OUT"],"sender":sender,"text":text}
        self.chat_log.append(msg)
        await self._broadcast_raw(msg)


# ─────────────────────── Server ──────────────────────────

lobbies: dict[str, GameLobby] = {}
tick_tasks: dict[str, asyncio.Task] = {}

async def lobby_tick_loop(lobby: GameLobby):
    interval = 1.0/TICK_RATE
    while lobby.running and lobby.players:
        await lobby.tick()
        await asyncio.sleep(interval)

async def handle_client(ws):
    pid  = str(uuid.uuid4())[:8]
    lobby: GameLobby | None = None
    player: Player | None   = None
    print(f"[+] Client connected: {pid}")

    async def send(obj):
        try: await ws.send(json.dumps(obj))
        except: pass

    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except:
                continue
            t = msg.get("type")

            # ── Lobby management ─────────────────────────
            if t == MSG["CREATE"]:
                name   = str(msg.get("name","Player"))[:16]
                lid    = rand_id()
                seed   = msg.get("seed", None)
                lobby  = GameLobby(lid, name, seed)
                lobbies[lid] = lobby
                player = lobby.add_player(pid, name)
                player.ws = ws
                await send({"type":MSG["JOINED"],"lobby_id":lid,"pid":pid,"is_host":True})
                await send(lobby.world_snapshot())
                # Start tick loop
                task = asyncio.ensure_future(lobby_tick_loop(lobby))
                tick_tasks[lid] = task
                print(f"  Lobby {lid} created by {name}")

            elif t == MSG["JOIN"]:
                lid  = str(msg.get("lobby_id","")).upper()
                name = str(msg.get("name","Player"))[:16]
                if lid not in lobbies:
                    await send({"type":MSG["ERROR"],"msg":"Lobby not found"})
                    continue
                lobby  = lobbies[lid]
                player = lobby.add_player(pid, name)
                player.ws = ws
                await send({"type":MSG["JOINED"],"lobby_id":lid,"pid":pid,"is_host":False})
                await send(lobby.world_snapshot())
                await lobby.broadcast_chat("Server", f"{name} joined the raft!")
                print(f"  {name} joined lobby {lid}")

            # ── In-game messages ─────────────────────────
            elif t == MSG["INPUT"] and player:
                player.input["dx"] = clamp(msg.get("dx",0),-1,1)
                player.input["dy"] = clamp(msg.get("dy",0),-1,1)
                if msg.get("attack"): lobby.player_attack(pid)

            elif t == MSG["CRAFT"] and lobby and player:
                item = str(msg.get("item",""))
                result = lobby.craft(pid, item)
                await send({"type":"craft_result","item":item,"result":result,"inv":player.inventory})

            elif t == MSG["FUEL"] and lobby:
                qty = int(msg.get("qty",10))
                lobby.add_fuel(pid, qty)

            elif t == MSG["PLACE"] and lobby:
                tx   = int(msg.get("tx",0))
                ty   = int(msg.get("ty",0))
                tile = int(msg.get("tile", T_RAFT))
                lobby.place_tile(pid, tx, ty, tile)

            elif t == MSG["CHAT"] and lobby:
                text = str(msg.get("text",""))[:120]
                await lobby.broadcast_chat(player.name if player else "?", text)

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        print(f"[-] Client disconnected: {pid} ({player.name if player else '?'})")
        if lobby and player:
            lobby.remove_player(pid)
            await lobby.broadcast_chat("Server", f"{player.name} left.")
            if not lobby.players:
                lobby.running = False
                lobbies.pop(lobby.id, None)
                tick_tasks.pop(lobby.id, None)
                print(f"  Lobby {lobby.id} closed (empty)")


async def main():
    host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT
    print(f"""
╔══════════════════════════════════════════╗
║        RAFT SURVIVORS — Server           ║
║  Listening on  {host}:{port:<5}            ║
╚══════════════════════════════════════════╝
""")
    async with websockets.serve(handle_client, host, port, ping_interval=20, ping_timeout=30):
        await asyncio.Future()   # run forever

if __name__ == "__main__":
    asyncio.run(main())
