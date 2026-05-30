#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║              RAFT SURVIVORS — Client                     ║
║  python client.py [server_ip] [port]                     ║
╚══════════════════════════════════════════════════════════╝
"""

import pygame, sys, json, math, asyncio, threading, time, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import websockets
from shared.constants import *

# ────────────────── Display config ───────────────────────
SCREEN_W, SCREEN_H = 960, 640
TILE_PX  = 20          # pixels per tile on screen
CAM_TILES_X = SCREEN_W // TILE_PX + 2
CAM_TILES_Y = SCREEN_H // TILE_PX + 2
FPS      = 60

# ──────────────── Pixel-art color palette ────────────────
PAL = {
    "ocean_deep":   (10,  40,  80),
    "ocean_mid":    (15,  60, 110),
    "ocean_foam":   (30,  90, 145),
    "ocean_light":  (50, 120, 180),
    "raft_wood":    (120, 80, 40),
    "raft_plank":   (100, 65, 30),
    "raft_edge":    (80,  50, 20),
    "island_dirt":  (120,100, 60),
    "island_grass": (60, 120, 50),
    "sand":         (220,195,140),
    "tree_trunk":   (80,  55, 30),
    "tree_leaf":    (30, 100, 30),
    "rock":         (120,115,110),
    "rock_shadow":  (80,  75, 70),
    "fire_y":       (255,210,  0),
    "fire_o":       (255,140,  0),
    "fire_r":       (220, 60, 20),
    "night_sky":    (10,  10, 30),
    "night_fog":    (20,  20, 60),
    "safe_glow":    (80, 160,255),
    "hud_bg":       (20,  25, 35),
    "hud_border":   (60,  80,120),
    "hp_red":       (200, 40, 40),
    "hunger_yellow":(220,180, 40),
    "fuel_blue":    (60, 130,220),
    "text_main":    (220,225,240),
    "text_dim":     (120,130,150),
    "menu_bg":      (8,   12, 22),
    "menu_card":    (18,  24, 40),
    "menu_accent":  (60, 180,255),
    "menu_hover":   (30,  50, 90),
    "monster_crawl":(160, 40, 40),
    "monster_brute":(120, 20, 20),
    "monster_shadow":(60, 20,100),
    "monster_eye":  (255,240,  0),
    "player_body":  (80, 160,240),
    "player_hat":   (40,  80,160),
    "player_skin":  (220,175,130),
    "chat_bg":      (10,  15, 25,180),
    "white":        (255,255,255),
    "black":        (0,   0,  0),
    "green":        (50, 200, 80),
    "warning_red":  (255, 60, 60),
}

def c(name): return PAL[name]

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

# ─────────────────── Pixel Art Renderer ──────────────────

class PixelArtRenderer:
    """Draws all game tiles and sprites using only pygame primitives — zero images needed."""

    def __init__(self, surf):
        self.surf = surf

    def tile(self, tile_type, x, y, size, anim=0):
        s = size
        r = pygame.Rect(x, y, s, s)
        t = tile_type

        if t == T_WATER:
            wave = int(math.sin(anim*2 + (x+y)*0.3)*2)
            pygame.draw.rect(self.surf, c("ocean_mid"), r)
            for i in range(0, s, 4):
                wx = x + i
                wy = y + s//2 + wave
                if wy < y+s:
                    pygame.draw.line(self.surf, c("ocean_light"), (wx,wy),(wx+2,wy),1)

        elif t in (T_RAFT, T_PLANK):
            pygame.draw.rect(self.surf, c("raft_wood"), r)
            for i in range(0, s, 5):
                pygame.draw.line(self.surf, c("raft_edge"), (x,y+i),(x+s,y+i),1)
            pygame.draw.rect(self.surf, c("raft_edge"), r, 1)

        elif t == T_WALL:
            pygame.draw.rect(self.surf, (80,70,60), r)
            for bx in range(x, x+s, 6):
                for by in range(y, y+s, 4):
                    pygame.draw.rect(self.surf, (60,50,40), (bx,by,5,3))
            pygame.draw.rect(self.surf, (50,40,30), r, 1)

        elif t == T_ISLAND:
            pygame.draw.rect(self.surf, c("island_grass"), r)
            pygame.draw.rect(self.surf, c("island_dirt"), (x,y+s*3//4,s,s//4))

        elif t == T_SAND:
            pygame.draw.rect(self.surf, c("sand"), r)

        elif t == T_TREE:
            pygame.draw.rect(self.surf, c("island_grass"), r)
            # trunk
            tw = s//4; th = s//2
            pygame.draw.rect(self.surf, c("tree_trunk"),
                             (x+s//2-tw//2, y+s//2, tw, th))
            # canopy
            pygame.draw.polygon(self.surf, c("tree_leaf"), [
                (x+s//2, y+2),
                (x+2,    y+s//2+2),
                (x+s-2,  y+s//2+2),
            ])
            pygame.draw.polygon(self.surf, (40,130,40), [
                (x+s//2, y+6),
                (x+4,    y+s//2+4),
                (x+s-4,  y+s//2+4),
            ])

        elif t == T_ROCK:
            pygame.draw.rect(self.surf, c("island_grass"), r)
            cx2, cy2 = x+s//2, y+s//2
            pygame.draw.ellipse(self.surf, c("rock"), (x+2,y+4,s-4,s-6))
            pygame.draw.ellipse(self.surf, c("rock_shadow"), (x+2,y+4,s//2,s//2-2))

        elif t == T_FIRE:
            pygame.draw.rect(self.surf, c("raft_wood"), r)
            # animated flames
            fl = int(math.sin(anim*5)*2)
            pygame.draw.polygon(self.surf, c("fire_r"), [
                (x+s//2, y+fl),
                (x+3,    y+s-3),
                (x+s-3,  y+s-3),
            ])
            pygame.draw.polygon(self.surf, c("fire_o"), [
                (x+s//2, y+4+fl),
                (x+5,    y+s-3),
                (x+s-5,  y+s-3),
            ])
            pygame.draw.polygon(self.surf, c("fire_y"), [
                (x+s//2, y+8+fl),
                (x+7,    y+s-3),
                (x+s-7,  y+s-3),
            ])

        elif t == T_TORCH:
            pygame.draw.rect(self.surf, c("raft_wood"), r)
            mx = x+s//2
            pygame.draw.line(self.surf, c("tree_trunk"),(mx,y+s-4),(mx,y+s//2),2)
            fl = int(math.sin(anim*6)*1)
            pygame.draw.circle(self.surf, c("fire_o"), (mx, y+s//2+fl), 3)
            pygame.draw.circle(self.surf, c("fire_y"), (mx, y+s//2+fl), 2)

    def player(self, x, y, size, color_body=None, facing=0, name="", is_self=False):
        s = size
        bc = color_body or c("player_body")
        # Shadow
        pygame.draw.ellipse(self.surf, (0,0,0,80), (x+2, y+s-4, s-4, 4))
        # Body
        pygame.draw.rect(self.surf, bc, (x+s//4, y+s//3, s//2, s//2+2), border_radius=3)
        # Head
        pygame.draw.circle(self.surf, c("player_skin"), (x+s//2, y+s//4), s//5)
        # Hat
        if is_self:
            pygame.draw.rect(self.surf, c("player_hat"), (x+s//4-1, y+s//4-s//5-2, s//2+2, 4))
        # Eyes
        ey = y+s//4
        pygame.draw.circle(self.surf, c("black"), (x+s//2-2, ey), 1)
        pygame.draw.circle(self.surf, c("black"), (x+s//2+2, ey), 1)
        # Name tag
        if name:
            font = pygame.font.SysFont("monospace", 9, bold=True)
            surf = font.render(name, True, c("white"))
            nx = x + s//2 - surf.get_width()//2
            ny = y - 12
            bg = pygame.Surface((surf.get_width()+4, 10), pygame.SRCALPHA)
            bg.fill((0,0,0,140))
            self.surf.blit(bg, (nx-2, ny))
            self.surf.blit(surf, (nx, ny))

    def monster(self, kind, x, y, size, hp_frac, anim=0):
        s = size
        bob = int(math.sin(anim*4)*1.5)
        if kind == "crawler":
            col = c("monster_crawl")
            # low crawling body
            pygame.draw.ellipse(self.surf, col, (x+1, y+s//2+bob, s-2, s//2-2))
            # claws
            for cx2 in [x+3, x+s-6]:
                pygame.draw.line(self.surf, col, (cx2,y+s//2+bob),(cx2-3,y+s-2+bob),2)
                pygame.draw.line(self.surf, col, (cx2,y+s//2+bob),(cx2+3,y+s-2+bob),2)
            # eyes
            pygame.draw.circle(self.surf,c("monster_eye"),(x+s//3,y+s//2+bob),2)
            pygame.draw.circle(self.surf,c("monster_eye"),(x+2*s//3,y+s//2+bob),2)

        elif kind == "brute":
            col = c("monster_brute")
            # big body
            pygame.draw.rect(self.surf, col, (x+2,y+s//4+bob,s-4,3*s//4-2), border_radius=2)
            # head
            pygame.draw.rect(self.surf, col, (x+s//4,y+bob,s//2,s//3))
            # spikes
            for sx in [x+1, x+s-4]:
                pygame.draw.polygon(self.surf,(140,20,20),[
                    (sx,y+s//4+bob),(sx+3,y+bob),(sx+6,y+s//4+bob)
                ])
            # eyes
            pygame.draw.circle(self.surf,c("monster_eye"),(x+s//3,y+s//6+bob),3)
            pygame.draw.circle(self.surf,c("monster_eye"),(x+2*s//3,y+s//6+bob),3)

        elif kind == "shadow":
            col = c("monster_shadow")
            # ghostly wisp
            pygame.draw.ellipse(self.surf, col, (x+2,y+s//3+bob,s-4,2*s//3-2))
            pygame.draw.ellipse(self.surf, (80,30,130), (x+4,y+s//3+bob+2,s-8,s//3))
            # glowing eyes
            pygame.draw.circle(self.surf,(255,200,255),(x+s//3,y+s//2+bob),3)
            pygame.draw.circle(self.surf,(255,200,255),(x+2*s//3,y+s//2+bob),3)
            pygame.draw.circle(self.surf,(255,255,255),(x+s//3,y+s//2+bob),1)
            pygame.draw.circle(self.surf,(255,255,255),(x+2*s//3,y+s//2+bob),1)

        # HP bar
        bar_y = y - 4
        pygame.draw.rect(self.surf, (80,0,0), (x, bar_y, s, 3))
        pygame.draw.rect(self.surf, c("hp_red"), (x, bar_y, int(s*hp_frac), 3))

    def chest(self, x, y, size):
        s = size
        pygame.draw.rect(self.surf, (140,100,40), (x+1,y+1,s-2,s-2), border_radius=2)
        pygame.draw.rect(self.surf, (100,70,20), (x+1,y+s//2,s-2,s//2-1))
        pygame.draw.rect(self.surf, (200,170,60), (x+s//4,y+s//2-2,s//2,4), border_radius=2)
        pygame.draw.circle(self.surf,(230,200,80),(x+s//2,y+s//2),2)
        pygame.draw.rect(self.surf, (80,55,15), (x+1,y+1,s-2,s-2), border_radius=2, width=1)

    def safe_zone_glow(self, cx, cy, radius_px, fuel_frac, anim):
        if fuel_frac <= 0: return
        alpha = int(fuel_frac * 80 * (0.85 + 0.15*math.sin(anim*2)))
        glow_surf = pygame.Surface((radius_px*2+4, radius_px*2+4), pygame.SRCALPHA)
        for r in range(radius_px, 0, -4):
            a = int(alpha * (r/radius_px)**2)
            a = min(a, 255)
            col = (*c("safe_glow"), a)
            pygame.draw.circle(glow_surf, col, (radius_px+2, radius_px+2), r)
        self.surf.blit(glow_surf, (cx-radius_px-2, cy-radius_px-2),
                       special_flags=pygame.BLEND_RGBA_ADD)

    def night_overlay(self, is_night, beacon_fuel, beacon_cx, beacon_cy, beacon_r_px):
        if not is_night: return
        darkness = max(0, min(200, int(200 * (1 - beacon_fuel/BEACON_MAX_FUEL*0.4))))
        ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        ov.fill((*c("night_sky"), darkness))
        # Cut out safe zone as lighter area
        if beacon_fuel > 0:
            for r in range(beacon_r_px, 0, -2):
                a2 = int(darkness * (r/beacon_r_px)**1.5)
                pygame.draw.circle(ov, (*c("night_sky"), max(0,a2-40)),
                                   (beacon_cx, beacon_cy), r)
        self.surf.blit(ov, (0,0), special_flags=pygame.BLEND_RGBA_ADD)

# ─────────────────────── Network thread ──────────────────

class NetClient:
    def __init__(self):
        self.state     = {}
        self.world     = None
        self.messages  = []       # incoming protocol messages
        self.chat_log  = []
        self._outbox   = []
        self._ws       = None
        self._loop     = None
        self._thread   = None
        self.connected = False
        self.pid       = None
        self.lobby_id  = None

    def connect(self, host, port):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run, args=(host, port), daemon=True)
        self._thread.start()

    def _run(self, host, port):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main(host, port))

    async def _main(self, host, port):
        uri = f"ws://{host}:{port}"
        try:
            async with websockets.connect(uri, ping_interval=15) as ws:
                self._ws = ws
                self.connected = True
                recv_task = asyncio.ensure_future(self._recv_loop(ws))
                send_task = asyncio.ensure_future(self._send_loop(ws))
                await asyncio.gather(recv_task, send_task)
        except Exception as e:
            self.messages.append({"type":"error","msg":str(e)})
            self.connected = False

    async def _recv_loop(self, ws):
        async for raw in ws:
            try:
                msg = json.loads(raw)
                t   = msg.get("type")
                if t == MSG["STATE"]:
                    self.state = msg
                elif t == MSG["WORLD"]:
                    self.world = msg
                elif t == MSG["CHAT_OUT"]:
                    self.chat_log.append(msg)
                    if len(self.chat_log) > 50: self.chat_log.pop(0)
                elif t == MSG["JOINED"]:
                    self.pid      = msg.get("pid")
                    self.lobby_id = msg.get("lobby_id")
                    self.messages.append(msg)
                else:
                    self.messages.append(msg)
            except: pass

    async def _send_loop(self, ws):
        while True:
            while self._outbox:
                data = self._outbox.pop(0)
                await ws.send(json.dumps(data))
            await asyncio.sleep(0.016)

    def send(self, obj):
        self._outbox.append(obj)

    def create_lobby(self, name):
        self.send({"type": MSG["CREATE"], "name": name})

    def join_lobby(self, lobby_id, name):
        self.send({"type": MSG["JOIN"], "lobby_id": lobby_id, "name": name})

    def send_input(self, dx, dy, attack=False):
        self.send({"type": MSG["INPUT"], "dx":dx, "dy":dy, "attack":attack})

    def send_craft(self, item):
        self.send({"type": MSG["CRAFT"], "item":item})

    def send_fuel(self, qty=10):
        self.send({"type": MSG["FUEL"], "qty":qty})

    def send_place(self, tx, ty, tile):
        self.send({"type": MSG["PLACE"], "tx":tx, "ty":ty, "tile":tile})

    def send_chat(self, text):
        self.send({"type": MSG["CHAT"], "text":text})


# ─────────────────────── HUD helpers ─────────────────────

class HUD:
    def __init__(self, screen):
        self.screen = screen
        self.font_sm = pygame.font.SysFont("monospace", 11, bold=True)
        self.font_md = pygame.font.SysFont("monospace", 14, bold=True)
        self.font_lg = pygame.font.SysFont("monospace", 20, bold=True)
        self.font_xl = pygame.font.SysFont("monospace", 28, bold=True)
        self.notifications = []    # (text, color, expire_time)

    def bar(self, x, y, w, h, frac, fg_color, label=""):
        frac = max(0.0, min(1.0, frac))
        pygame.draw.rect(self.screen, (30,30,40), (x,y,w,h), border_radius=3)
        pygame.draw.rect(self.screen, fg_color,   (x,y,int(w*frac),h), border_radius=3)
        pygame.draw.rect(self.screen, c("hud_border"),(x,y,w,h),1, border_radius=3)
        if label:
            t = self.font_sm.render(label, True, c("white"))
            self.screen.blit(t, (x+2, y+1))

    def text(self, txt, x, y, font=None, color=None):
        font  = font or self.font_sm
        color = color or c("text_main")
        surf  = font.render(str(txt), True, color)
        self.screen.blit(surf, (x,y))
        return surf.get_width()

    def panel(self, x, y, w, h, alpha=200, border=True):
        s = pygame.Surface((w,h), pygame.SRCALPHA)
        s.fill((*c("hud_bg"), alpha))
        self.screen.blit(s, (x,y))
        if border:
            pygame.draw.rect(self.screen, c("hud_border"), (x,y,w,h), 1, border_radius=3)

    def notify(self, text, color=None):
        color = color or c("text_main")
        self.notifications.append((text, color, time.time()+3.0))

    def draw_notifications(self):
        now = time.time()
        self.notifications = [(t,col,exp) for t,col,exp in self.notifications if exp>now]
        for i,(txt,col,exp) in enumerate(self.notifications[-5:]):
            fade = min(1.0,(exp-now)/0.5)
            x = SCREEN_W//2
            y = SCREEN_H - 120 - i*20
            surf = self.font_md.render(txt, True, col)
            surf.set_alpha(int(fade*220))
            self.screen.blit(surf, (x-surf.get_width()//2, y))

    def draw_player_stats(self, player_data):
        if not player_data: return
        x, y = 10, SCREEN_H-70
        self.panel(x-4, y-4, 200, 68)
        hp = player_data.get("hp",100)/PLAYER_MAX_HP
        hunger = player_data.get("hunger",100)/PLAYER_MAX_HUNGER
        self.bar(x, y,    180, 12, hp,     c("hp_red"),       f"HP {int(player_data.get('hp',100))}")
        self.bar(x, y+16, 180, 12, hunger, c("hunger_yellow"),f"HUNGER {int(player_data.get('hunger',100))}")
        safe = player_data.get("safe",True)
        status = "✔ SAFE" if safe else "✖ DANGER"
        scol   = c("green") if safe else c("warning_red")
        self.text(status, x, y+32, color=scol)

    def draw_beacon(self, fuel, is_night):
        x, y = SCREEN_W-210, SCREEN_H-70
        self.panel(x-4, y-4, 200, 60)
        frac = fuel/BEACON_MAX_FUEL
        col  = c("fuel_blue") if fuel > 20 else c("warning_red")
        self.bar(x, y, 180, 12, frac, col, f"BEACON {int(fuel)}/{BEACON_MAX_FUEL}")
        phase = "NIGHT" if is_night else "DAY"
        pcol  = c("warning_red") if is_night else (220,200,80)
        self.text(f"● {phase}", x, y+18, color=pcol)

    def draw_inventory(self, inv):
        if not inv: return
        x, y = 10, 10
        self.panel(x-4, y-4, SCREEN_W//2, 26)
        xi = x
        for item, qty in inv.items():
            if qty <= 0: continue
            txt = f"[{item[0].upper()}:{qty}]"
            w = self.text(txt, xi, y+2, color=c("text_main"))
            xi += w + 4

    def draw_phase_timer(self, remaining, is_night):
        label = f"{'☽ NIGHT' if is_night else '☀ DAY'} {int(remaining)}s"
        col   = c("warning_red") if is_night else (220,200,80)
        w     = self.font_md.render(label, True, col).get_width()
        x     = SCREEN_W//2 - w//2
        self.text(label, x, 8, font=self.font_md, color=col)

    def draw_chat(self, chat_log, chat_input, chat_open):
        panel_h = 120
        panel_w = 320
        x, y = 10, SCREEN_H - panel_h - 80
        self.panel(x-2, y-2, panel_w, panel_h, alpha=160, border=False)
        lines = chat_log[-6:]
        for i, msg in enumerate(lines):
            sender = msg.get("sender","?")
            text   = msg.get("text","")
            full   = f"{sender}: {text}"[:44]
            col    = (200,220,255) if sender!="Server" else (180,180,120)
            self.text(full, x, y+i*14, color=col)
        if chat_open:
            ibox_y = y + panel_h - 2
            self.panel(x-2, ibox_y, panel_w, 18, alpha=220)
            cursor = "_" if int(time.time()*2)%2 else ""
            self.text(f"> {chat_input}{cursor}", x, ibox_y+2, color=c("white"))

    def draw_night_warning(self, secs):
        txt = f"☽ NIGHT IN {secs}s — FUEL THE BEACON!"
        surf = self.font_lg.render(txt, True, c("warning_red"))
        surf.set_alpha(int(200*(0.7+0.3*math.sin(time.time()*6))))
        self.screen.blit(surf, (SCREEN_W//2-surf.get_width()//2, SCREEN_H//3))

    def draw_craft_menu(self, inv):
        pw, ph = 260, 30 + len(RECIPES)*22 + 10
        x = SCREEN_W//2 - pw//2
        y = SCREEN_H//2 - ph//2
        self.panel(x, y, pw, ph, alpha=240)
        self.text("─ CRAFTING ─", x+10, y+6, font=self.font_md, color=c("menu_accent"))
        for i,(item,recipe) in enumerate(RECIPES.items()):
            iy = y+28+i*22
            can = all(inv.get(ing,0)>=qty for ing,qty in recipe.items())
            col = c("green") if can else c("text_dim")
            req = " ".join(f"{q}{k[0].upper()}" for k,q in recipe.items())
            self.text(f"[{i+1}] {item:<8} ← {req}", x+10, iy, color=col)
        self.text("E to close · 1-5 to craft", x+10, y+ph-16, color=c("text_dim"))

    def draw_death_screen(self):
        ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        ov.fill((60,0,0,160))
        self.screen.blit(ov,(0,0))
        self.text("YOU DIED", SCREEN_W//2-80, SCREEN_H//2-20, font=self.font_xl, color=c("warning_red"))
        self.text("Waiting for respawn...", SCREEN_W//2-80, SCREEN_H//2+20, color=c("text_dim"))


# ─────────────────────── Menu Screen ─────────────────────

class MenuScreen:
    def __init__(self, screen, default_host="127.0.0.1", default_port=DEFAULT_PORT):
        self.screen = screen
        self.font_xl = pygame.font.SysFont("monospace",36,bold=True)
        self.font_lg = pygame.font.SysFont("monospace",22,bold=True)
        self.font_md = pygame.font.SysFont("monospace",15,bold=True)
        self.font_sm = pygame.font.SysFont("monospace",12)
        self.state   = "main"   # main | create | join | connecting
        self.name_buf   = "Player"
        self.lobby_buf  = ""
        self.host_buf   = default_host
        self.port_buf   = str(default_port)
        self.active_field = "name"
        self.anim    = 0.0
        self.error   = ""

    def draw(self, dt):
        self.anim += dt
        self.screen.fill(c("menu_bg"))
        self._draw_ocean_bg()
        if self.state == "main":       self._draw_main()
        elif self.state == "create":   self._draw_create()
        elif self.state == "join":     self._draw_join()
        elif self.state == "connecting": self._draw_connecting()

    def _draw_ocean_bg(self):
        for yi in range(0, SCREEN_H, 14):
            phase = math.sin(self.anim*0.5 + yi*0.08)*6
            col   = (10+int(phase),40,80)
            pygame.draw.line(self.screen, col, (0,yi),(SCREEN_W,yi), 2)

        # Floating raft
        rx = SCREEN_W//2 + int(math.sin(self.anim*0.4)*8) - 60
        ry = SCREEN_H//2 + int(math.cos(self.anim*0.3)*4) + 80
        for i in range(5):
            pygame.draw.rect(self.screen, c("raft_wood"), (rx+i*24, ry, 22, 14))
            pygame.draw.rect(self.screen, c("raft_edge"), (rx+i*24, ry, 22, 14), 1)

    def _field(self, label, value, active, x, y, w=280):
        col = c("menu_accent") if active else c("hud_border")
        pygame.draw.rect(self.screen, c("menu_card"), (x,y,w,26), border_radius=4)
        pygame.draw.rect(self.screen, col, (x,y,w,26), 1, border_radius=4)
        t = self.font_sm.render(f"{label}: {value}" + ("_" if active and int(self.anim*2)%2 else ""),
                                True, c("text_main"))
        self.screen.blit(t, (x+8, y+6))

    def _button(self, text, x, y, w=160, h=36, hover=False):
        col = c("menu_hover") if hover else c("menu_card")
        pygame.draw.rect(self.screen, col, (x,y,w,h), border_radius=6)
        pygame.draw.rect(self.screen, c("menu_accent"), (x,y,w,h), 1, border_radius=6)
        t = self.font_md.render(text, True, c("menu_accent"))
        self.screen.blit(t, (x+w//2-t.get_width()//2, y+h//2-t.get_height()//2))

    def _draw_main(self):
        # Title
        t1 = self.font_xl.render("RAFT", True, (255,180,30))
        t2 = self.font_xl.render("SURVIVORS", True, c("menu_accent"))
        self.screen.blit(t1, (SCREEN_W//2-t1.get_width()//2, 80))
        self.screen.blit(t2, (SCREEN_W//2-t2.get_width()//2, 120))
        sub = self.font_sm.render("Survive the night. Fuel the beacon. Don't die.", True, c("text_dim"))
        self.screen.blit(sub, (SCREEN_W//2-sub.get_width()//2, 165))

        mx, my = pygame.mouse.get_pos()
        bx = SCREEN_W//2 - 100
        self._button("⚓ CREATE WORLD", bx, 240, hover=(bx<=mx<bx+200 and 240<=my<276))
        self._button("⚡ JOIN LOBBY",   bx, 290, hover=(bx<=mx<bx+200 and 290<=my<326))

        ctrl = self.font_sm.render("WASD=Move  SPACE=Attack  E=Craft  F=Fuel  T=Chat", True, c("text_dim"))
        self.screen.blit(ctrl, (SCREEN_W//2-ctrl.get_width()//2, SCREEN_H-40))

    def _draw_create(self):
        t = self.font_lg.render("CREATE WORLD", True, c("menu_accent"))
        self.screen.blit(t,(SCREEN_W//2-t.get_width()//2, 80))
        bx = SCREEN_W//2-140
        self._field("Name",  self.name_buf,  self.active_field=="name",  bx, 160)
        self._field("Host",  self.host_buf,  self.active_field=="host",  bx, 200)
        self._field("Port",  self.port_buf,  self.active_field=="port",  bx, 240)
        self._button("▶ START", bx+60, 290, w=160)
        back = self.font_sm.render("ESC to go back", True, c("text_dim"))
        self.screen.blit(back, (bx, 340))
        if self.error:
            err = self.font_sm.render(self.error, True, c("warning_red"))
            self.screen.blit(err, (bx, 370))

    def _draw_join(self):
        t = self.font_lg.render("JOIN LOBBY", True, c("menu_accent"))
        self.screen.blit(t,(SCREEN_W//2-t.get_width()//2, 80))
        bx = SCREEN_W//2-140
        self._field("Name",     self.name_buf,  self.active_field=="name",     bx, 160)
        self._field("Lobby ID", self.lobby_buf, self.active_field=="lobby",    bx, 200)
        self._field("Host",     self.host_buf,  self.active_field=="host",     bx, 240)
        self._field("Port",     self.port_buf,  self.active_field=="port",     bx, 280)
        self._button("▶ CONNECT", bx+60, 325, w=160)
        back = self.font_sm.render("ESC to go back", True, c("text_dim"))
        self.screen.blit(back, (bx, 380))
        if self.error:
            err = self.font_sm.render(self.error, True, c("warning_red"))
            self.screen.blit(err, (bx, 410))

    def _draw_connecting(self):
        dots = "."*((int(self.anim*2)%4))
        t = self.font_lg.render(f"Connecting{dots}", True, c("menu_accent"))
        self.screen.blit(t,(SCREEN_W//2-t.get_width()//2, SCREEN_H//2))

    def handle_event(self, e):
        """Returns ('create',name,host,port) / ('join',name,id,host,port) / None"""
        if e.type == pygame.KEYDOWN:
            if self.state == "main":
                pass
            elif self.state in ("create","join"):
                if e.key == pygame.K_ESCAPE:
                    self.state = "main"; self.error = ""; return None
                if e.key == pygame.K_TAB:
                    fields = ["name","host","port"] if self.state=="create" else ["name","lobby","host","port"]
                    idx    = fields.index(self.active_field) if self.active_field in fields else 0
                    self.active_field = fields[(idx+1)%len(fields)]
                if e.key == pygame.K_BACKSPACE:
                    target = getattr(self, f"{self.active_field}_buf")
                    setattr(self, f"{self.active_field}_buf", target[:-1])
                elif e.key == pygame.K_RETURN:
                    return self._submit()
                else:
                    ch = e.unicode
                    if ch and ch.isprintable():
                        setattr(self, f"{self.active_field}_buf",
                                getattr(self, f"{self.active_field}_buf") + ch)

        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            bx = SCREEN_W//2-100
            if self.state == "main":
                if bx<=mx<bx+200 and 240<=my<276:
                    self.state="create"; self.active_field="name"
                elif bx<=mx<bx+200 and 290<=my<326:
                    self.state="join";   self.active_field="name"
            elif self.state in ("create","join"):
                if bx<=mx<bx+200:
                    if self.state=="create" and 290<=my<326: return self._submit()
                    if self.state=="join"   and 325<=my<361: return self._submit()
                # Field click detection
                field_map = {"name":160,"host":200,"port":240}
                if self.state=="join": field_map["lobby"]=200; field_map["host"]=240; field_map["port"]=280
                fbx = SCREEN_W//2-140
                for fname, fy in field_map.items():
                    if fbx<=mx<fbx+280 and fy<=my<fy+26:
                        self.active_field = fname
        return None

    def _submit(self):
        name = self.name_buf.strip() or "Player"
        host = self.host_buf.strip() or "127.0.0.1"
        try:
            port = int(self.port_buf.strip())
        except:
            self.error = "Invalid port"; return None
        if self.state == "create":
            self.state = "connecting"
            return ("create", name, host, port)
        else:
            lid = self.lobby_buf.strip().upper()
            if not lid:
                self.error = "Enter a lobby ID"; return None
            self.state = "connecting"
            return ("join", name, lid, host, port)


# ─────────────────────── Main Game ───────────────────────

class RaftGame:
    def __init__(self, host, port):
        pygame.init()
        pygame.display.set_caption("Raft Survivors")
        self.screen   = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.clock    = pygame.time.Clock()
        self.net      = NetClient()
        self.hud      = HUD(self.screen)
        self.art      = PixelArtRenderer(self.screen)
        self.menu     = MenuScreen(self.screen, host, port)
        self.in_game  = False
        self.cam_x    = 0.0      # camera tile offset
        self.cam_y    = 0.0
        self.my_pid   = None
        self.anim     = 0.0
        self.chat_open= False
        self.chat_input=""
        self.craft_open=False
        self.night_warn_timer=0.0
        self.show_night_warn=False
        self.player_colors= {}    # pid → color
        self._colors_pool  = [
            (80,200,120),(200,120,80),(200,80,200),(120,200,200),
            (220,180,60),(180,60,220),(60,220,180),(220,100,100),
        ]
        self._color_idx = 0

    def run(self):
        dt = 0.0
        while True:
            dt = self.clock.tick(FPS)/1000.0
            self.anim += dt
            self._process_events(dt)
            self._process_net()
            if self.in_game:
                self._update_camera()
                self._draw_game()
            else:
                self.menu.draw(dt)
            pygame.display.flip()

    def _process_events(self, dt):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            if not self.in_game:
                result = self.menu.handle_event(e)
                if result:
                    if result[0] == "create":
                        _, name, host, port = result
                        self.net.connect(host, port)
                        self.net.create_lobby(name)
                    elif result[0] == "join":
                        _, name, lid, host, port = result
                        self.net.connect(host, port)
                        self.net.join_lobby(lid, name)
                continue

            # In-game events
            if e.type == pygame.KEYDOWN:
                if self.chat_open:
                    if e.key == pygame.K_RETURN:
                        if self.chat_input.strip():
                            self.net.send_chat(self.chat_input)
                        self.chat_input = ""
                        self.chat_open  = False
                    elif e.key == pygame.K_ESCAPE:
                        self.chat_open = False; self.chat_input = ""
                    elif e.key == pygame.K_BACKSPACE:
                        self.chat_input = self.chat_input[:-1]
                    else:
                        if e.unicode and e.unicode.isprintable():
                            self.chat_input += e.unicode
                elif self.craft_open:
                    if e.key == pygame.K_e or e.key == pygame.K_ESCAPE:
                        self.craft_open = False
                    for i,(item,_) in enumerate(RECIPES.items()):
                        if e.key == getattr(pygame,f"K_{i+1}",None):
                            self.net.send_craft(item)
                            self.hud.notify(f"Crafting {item}...", c("menu_accent"))
                else:
                    if e.key == pygame.K_t:
                        self.chat_open = True
                    elif e.key == pygame.K_e:
                        self.craft_open = not self.craft_open
                    elif e.key == pygame.K_f:
                        self.net.send_fuel(10)
                        self.hud.notify("Added fuel to beacon!", c("fuel_blue"))
                    elif e.key == pygame.K_SPACE:
                        keys = pygame.key.get_pressed()
                        dx = (keys[pygame.K_d]-keys[pygame.K_a]) or (keys[pygame.K_RIGHT]-keys[pygame.K_LEFT])
                        dy = (keys[pygame.K_s]-keys[pygame.K_w]) or (keys[pygame.K_DOWN]-keys[pygame.K_UP])
                        self.net.send_input(dx, dy, attack=True)

        if self.in_game and not self.chat_open and not self.craft_open:
            keys = pygame.key.get_pressed()
            dx = (keys[pygame.K_d] - keys[pygame.K_a]) + (keys[pygame.K_RIGHT]-keys[pygame.K_LEFT])
            dy = (keys[pygame.K_s] - keys[pygame.K_w]) + (keys[pygame.K_DOWN]-keys[pygame.K_UP])
            attack = keys[pygame.K_SPACE]
            self.net.send_input(
                clamp(dx,-1,1),
                clamp(dy,-1,1),
                bool(attack)
            )

    def _process_net(self):
        while self.net.messages:
            msg = self.net.messages.pop(0)
            t   = msg.get("type")
            if t == MSG["JOINED"]:
                self.my_pid  = msg.get("pid")
                self.in_game = True
                self.hud.notify(f"Joined lobby {msg.get('lobby_id')}!", c("menu_accent"))
            elif t == MSG["ERROR"]:
                self.menu.error = msg.get("msg","Connection error")
                self.menu.state = "create" if "create" in str(msg) else "join"
            elif t == MSG["NIGHT_WARN"]:
                self.show_night_warn  = True
                self.night_warn_timer = msg.get("secs",10)
            elif t == MSG["LOOT"]:
                items = msg.get("items",{})
                summary = " ".join(f"+{v}{k[0].upper()}" for k,v in items.items())
                self.hud.notify(f"Chest! {summary}", (220,200,80))
            elif t == MSG["DEATH"]:
                self.hud.notify("You died! Respawning...", c("warning_red"))
            elif t == "craft_result":
                res = msg.get("result")
                item = msg.get("item","")
                if res == "ok":
                    self.hud.notify(f"Crafted {item}!", c("green"))
                elif res == "no_materials":
                    self.hud.notify(f"Not enough materials for {item}", c("warning_red"))
            elif t == MSG["PLAYER_JOINED"]:
                self.hud.notify(f"{msg.get('name','?')} joined!", c("menu_accent"))

    def _update_camera(self):
        state = self.net.state
        if not state: return
        me = next((p for p in state.get("players",[]) if p["id"]==self.my_pid), None)
        if not me: return
        target_cx = me["x"] - (SCREEN_W/2)/TILE_PX
        target_cy = me["y"] - (SCREEN_H/2)/TILE_PX
        self.cam_x += (target_cx - self.cam_x)*0.1
        self.cam_y += (target_cy - self.cam_y)*0.1
        self.cam_x = clamp(self.cam_x, 0, WORLD_W - SCREEN_W/TILE_PX)
        self.cam_y = clamp(self.cam_y, 0, WORLD_H - SCREEN_H/TILE_PX)

    def _world_to_screen(self, wx, wy):
        sx = (wx - self.cam_x)*TILE_PX
        sy = (wy - self.cam_y)*TILE_PX
        return int(sx), int(sy)

    def _draw_game(self):
        world = self.net.world
        state = self.net.state
        if not world or not state:
            self.screen.fill(c("ocean_deep"))
            t = self.hud.font_md.render("Loading...", True, c("text_dim"))
            self.screen.blit(t,(SCREEN_W//2-40,SCREEN_H//2))
            return

        is_night = state.get("is_night", False)
        fuel     = state.get("beacon_fuel", BEACON_MAX_FUEL)
        beacon   = world.get("beacon",[WORLD_W//2, WORLD_H//2])
        bsx, bsy = self._world_to_screen(beacon[0], beacon[1])

        # ── Background ───────────────────
        self.screen.fill(c("ocean_deep"))

        # ── Tiles ────────────────────────
        tiles = world.get("tiles",[])
        W     = world.get("w", WORLD_W)
        H     = world.get("h", WORLD_H)

        x0 = max(0, int(self.cam_x)-1)
        y0 = max(0, int(self.cam_y)-1)
        x1 = min(W, x0+CAM_TILES_X)
        y1 = min(H, y0+CAM_TILES_Y)

        for tx in range(x0, x1):
            for ty in range(y0, y1):
                tile_type = tiles[tx*H+ty] if tx*H+ty < len(tiles) else T_WATER
                sx, sy = self._world_to_screen(tx, ty)
                self.art.tile(tile_type, sx, sy, TILE_PX, self.anim)

        # ── Safe zone glow ────────────────
        r_px = int(BEACON_RADIUS * TILE_PX)
        self.art.safe_zone_glow(bsx+TILE_PX//2, bsy+TILE_PX//2, r_px, fuel/BEACON_MAX_FUEL, self.anim)

        # ── Chests ───────────────────────
        for chest in state.get("chests",[]):
            sx, sy = self._world_to_screen(chest["x"], chest["y"])
            self.art.chest(sx, sy, TILE_PX)

        # ── Monsters ─────────────────────
        for m in state.get("monsters",[]):
            sx, sy = self._world_to_screen(m["x"], m["y"])
            hp_frac = m["hp"]/m["max_hp"]
            self.art.monster(m["kind"], sx, sy, TILE_PX, hp_frac, self.anim)

        # ── Players ──────────────────────
        for p in state.get("players",[]):
            if p["id"] not in self.player_colors:
                col = self._colors_pool[self._color_idx % len(self._colors_pool)]
                self.player_colors[p["id"]] = col
                self._color_idx += 1
            sx, sy = self._world_to_screen(p["x"], p["y"])
            is_self = p["id"] == self.my_pid
            self.art.player(sx, sy, TILE_PX,
                            self.player_colors[p["id"]],
                            name=p["name"] if not is_self else "",
                            is_self=is_self)

        # ── Night overlay ─────────────────
        self.art.night_overlay(is_night, fuel, bsx+TILE_PX//2, bsy+TILE_PX//2, r_px)

        # ── HUD ───────────────────────────
        me = next((p for p in state.get("players",[]) if p["id"]==self.my_pid), None)
        self.hud.draw_inventory(me.get("inv") if me else {})
        self.hud.draw_phase_timer(state.get("phase_remaining",0), is_night)
        self.hud.draw_player_stats(me)
        self.hud.draw_beacon(fuel, is_night)
        self.hud.draw_chat(self.net.chat_log, self.chat_input, self.chat_open)
        self.hud.draw_notifications()

        if self.craft_open and me:
            self.hud.draw_craft_menu(me.get("inv",{}))

        if self.show_night_warn:
            self.night_warn_timer -= self.clock.get_time()/1000.0
            secs = max(0, int(self.night_warn_timer))
            if secs > 0:
                self.hud.draw_night_warning(secs)
            else:
                self.show_night_warn = False

        if me and not me.get("alive",True):
            self.hud.draw_death_screen()

        # Night counter
        nc = state.get("night_count",0)
        if nc > 0:
            self.hud.text(f"Night {nc}", SCREEN_W-80, 10, color=(160,140,200))


# ─────────────────────── Entry point ─────────────────────

if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT
    game = RaftGame(host, port)
    game.run()
