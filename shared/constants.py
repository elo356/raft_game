# ============================================================
#  RAFT SURVIVORS — Shared Constants & Protocol
# ============================================================

# Network
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 7777
TICK_RATE     = 20          # server ticks per second

# World
WORLD_W = 80                # tiles
WORLD_H = 60
TILE_SIZE = 16              # pixels per tile (client-side)

# Tiles
T_WATER   = 0
T_RAFT    = 1
T_PLANK   = 2
T_ISLAND  = 3
T_SAND    = 4
T_TREE    = 5
T_ROCK    = 6
T_CHEST   = 7
T_TORCH   = 8
T_WALL    = 9
T_FIRE    = 10

# Items
ITEMS = {
    "wood":    {"icon": "W", "stack": 99},
    "stone":   {"icon": "S", "stack": 99},
    "rope":    {"icon": "R", "stack": 50},
    "fuel":    {"icon": "F", "stack": 30},
    "plank":   {"icon": "P", "stack": 20},
    "food":    {"icon": "🍗", "stack": 10},
    "torch":   {"icon": "T", "stack": 5},
    "wall":    {"icon": "☐", "stack": 10},
}

# Day/Night
DAY_DURATION   = 90         # seconds
NIGHT_DURATION = 60         # seconds
DUSK_DURATION  = 10         # seconds

# Beacon (safe zone)
BEACON_MAX_FUEL = 100
BEACON_DRAIN    = 0.8       # fuel per second at night
BEACON_RADIUS   = 8         # tiles protected

# Player
PLAYER_SPEED    = 3.0       # tiles/second
PLAYER_MAX_HP   = 100
PLAYER_MAX_HUNGER = 100
HUNGER_DRAIN    = 0.02      # per second

# Monster
MONSTER_TYPES = {
    "crawler": {"hp": 30,  "dmg": 8,  "speed": 1.8, "range": 1.0, "xp": 10},
    "brute":   {"hp": 80,  "dmg": 20, "speed": 1.0, "range": 1.2, "xp": 25},
    "shadow":  {"hp": 50,  "dmg": 15, "speed": 2.5, "range": 0.8, "xp": 20},
}

# Protocol message types
MSG = {
    # C→S
    "JOIN":      "join",
    "CREATE":    "create",
    "INPUT":     "input",
    "INTERACT":  "interact",
    "CRAFT":     "craft",
    "FUEL":      "fuel",
    "PLACE":     "place",
    "CHAT":      "chat",

    # S→C
    "WORLD":     "world",
    "STATE":     "state",
    "DELTA":     "delta",
    "CHAT_OUT":  "chat_out",
    "ERROR":     "error",
    "JOINED":    "joined",
    "PLAYER_JOINED": "player_joined",
    "PLAYER_LEFT":   "player_left",
    "LOBBY_LIST":    "lobby_list",
    "NIGHT_WARN":    "night_warn",
    "DEATH":         "death",
    "LOOT":          "loot",
}

# Craft recipes  {result: {ingredient: qty, ...}}
RECIPES = {
    "plank":  {"wood": 3},
    "rope":   {"wood": 2, "stone": 1},
    "fuel":   {"wood": 5, "stone": 2},
    "torch":  {"wood": 2, "fuel": 1},
    "wall":   {"plank": 3, "rope": 1},
}
