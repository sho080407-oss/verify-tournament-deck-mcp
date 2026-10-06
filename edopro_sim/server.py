from __future__ import annotations

import contextlib
import ctypes as C
import json
import os
import random
import sqlite3
import struct
from collections import Counter
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

ROOT = Path(os.environ.get("EDOPRO_SIM_ROOT", "/opt/edopro-sim"))
LIB_PATH = ROOT / "lib" / "libocgcore.so"
SCRIPTS = ROOT / "CardScripts"
CDB_PATH = ROOT / "BabelCDB" / "cards.cdb"
FINGERPRINT_PATH = ROOT / "runtime-fingerprint.json"

LOCATION_DECK = 0x01
LOCATION_HAND = 0x02
LOCATION_MZONE = 0x04
LOCATION_SZONE = 0x08
LOCATION_GRAVE = 0x10
LOCATION_REMOVED = 0x20
LOCATION_EXTRA = 0x40

POS_FACEUP_ATTACK = 0x1
POS_FACEDOWN_ATTACK = 0x2
POS_FACEUP_DEFENSE = 0x4
POS_FACEDOWN_DEFENSE = 0x8
TYPE_LINK = 0x4000000

MSG_RETRY = 1
MSG_WIN = 5
MSG_SELECT_BATTLECMD = 10
MSG_SELECT_IDLECMD = 11
MSG_SELECT_EFFECTYN = 12
MSG_SELECT_YESNO = 13
MSG_SELECT_OPTION = 14
MSG_SELECT_CARD = 15
MSG_SELECT_CHAIN = 16
MSG_SELECT_PLACE = 18
MSG_SELECT_POSITION = 19
MSG_SELECT_TRIBUTE = 20
MSG_SORT_CHAIN = 21
MSG_SELECT_COUNTER = 22
MSG_SELECT_SUM = 23
MSG_SELECT_DISFIELD = 24
MSG_SORT_CARD = 25
MSG_SELECT_UNSELECT_CARD = 26
MSG_NEW_TURN = 40
MSG_NEW_PHASE = 41
MSG_SUMMONING = 60
MSG_SPSUMMONING = 62
MSG_FLIPSUMMONING = 64
MSG_ROCK_PAPER_SCISSORS = 132
MSG_ANNOUNCE_RACE = 140
MSG_ANNOUNCE_ATTRIB = 141
MSG_ANNOUNCE_CARD = 142
MSG_ANNOUNCE_NUMBER = 143

MSG_NAMES = {
    MSG_RETRY: "MSG_RETRY",
    MSG_WIN: "MSG_WIN",
    MSG_SELECT_BATTLECMD: "MSG_SELECT_BATTLECMD",
    MSG_SELECT_IDLECMD: "MSG_SELECT_IDLECMD",
    MSG_SELECT_EFFECTYN: "MSG_SELECT_EFFECTYN",
    MSG_SELECT_YESNO: "MSG_SELECT_YESNO",
    MSG_SELECT_OPTION: "MSG_SELECT_OPTION",
    MSG_SELECT_CARD: "MSG_SELECT_CARD",
    MSG_SELECT_CHAIN: "MSG_SELECT_CHAIN",
    MSG_SELECT_PLACE: "MSG_SELECT_PLACE",
    MSG_SELECT_POSITION: "MSG_SELECT_POSITION",
    MSG_SELECT_TRIBUTE: "MSG_SELECT_TRIBUTE",
    MSG_SORT_CHAIN: "MSG_SORT_CHAIN",
    MSG_SELECT_COUNTER: "MSG_SELECT_COUNTER",
    MSG_SELECT_SUM: "MSG_SELECT_SUM",
    MSG_SELECT_DISFIELD: "MSG_SELECT_DISFIELD",
    MSG_SORT_CARD: "MSG_SORT_CARD",
    MSG_SELECT_UNSELECT_CARD: "MSG_SELECT_UNSELECT_CARD",
    MSG_NEW_TURN: "MSG_NEW_TURN",
    MSG_NEW_PHASE: "MSG_NEW_PHASE",
    MSG_SUMMONING: "MSG_SUMMONING",
    MSG_SPSUMMONING: "MSG_SPSUMMONING",
    MSG_FLIPSUMMONING: "MSG_FLIPSUMMONING",
    MSG_ROCK_PAPER_SCISSORS: "MSG_ROCK_PAPER_SCISSORS",
    MSG_ANNOUNCE_RACE: "MSG_ANNOUNCE_RACE",
    MSG_ANNOUNCE_ATTRIB: "MSG_ANNOUNCE_ATTRIB",
    MSG_ANNOUNCE_CARD: "MSG_ANNOUNCE_CARD",
    MSG_ANNOUNCE_NUMBER: "MSG_ANNOUNCE_NUMBER",
}

# OCG Master Rule 5. TCG-only SEGOC flags are intentionally not enabled.
DUEL_PSEUDO_SHUFFLE = 0x10
DUEL_PZONE = 0x800
DUEL_EMZONE = 0x2000
DUEL_FSX_MMZONE = 0x4000
DUEL_TRAP_MONSTERS_NOT_USE_ZONE = 0x8000
DUEL_TRIGGER_ONLY_IN_LOCATION = 0x20000
DUEL_MODE_MR5 = (
    DUEL_PZONE
    | DUEL_EMZONE
    | DUEL_FSX_MMZONE
    | DUEL_TRAP_MONSTERS_NOT_USE_ZONE
    | DUEL_TRIGGER_ONLY_IN_LOCATION
)

OCG_DUEL_CREATION_SUCCESS = 0
OCG_DUEL_STATUS_END = 0
OCG_DUEL_STATUS_AWAITING = 1

IDLE_SUMMON = 0
IDLE_SPSUMMON = 1
IDLE_REPOS = 2
IDLE_MSET = 3
IDLE_SSET = 4
IDLE_ACTIVATE = 5
IDLE_TO_BP = 6
IDLE_TO_EP = 7

BATTLE_ACTIVATE = 0
BATTLE_ATTACK = 1
BATTLE_TO_M2 = 2
BATTLE_TO_EP = 3

# Inert opponent deck used only to let ocgcore start a duel.
DUMMY_OPPONENT = 69247929


class OCG_CardData(C.Structure):
    _fields_ = [
        ("code", C.c_uint32),
        ("alias", C.c_uint32),
        ("setcodes", C.POINTER(C.c_uint16)),
        ("type", C.c_uint32),
        ("level", C.c_uint32),
        ("attribute", C.c_uint32),
        ("race", C.c_uint64),
        ("attack", C.c_int32),
        ("defense", C.c_int32),
        ("lscale", C.c_uint32),
        ("rscale", C.c_uint32),
        ("link_marker", C.c_uint32),
    ]


class OCG_Player(C.Structure):
    _fields_ = [
        ("startingLP", C.c_uint32),
        ("startingDrawCount", C.c_uint32),
        ("drawCountPerTurn", C.c_uint32),
    ]


OCG_DataReader = C.CFUNCTYPE(None, C.c_void_p, C.c_uint32, C.POINTER(OCG_CardData))
OCG_DataReaderDone = C.CFUNCTYPE(None, C.c_void_p, C.POINTER(OCG_CardData))
OCG_ScriptReader = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p, C.c_char_p)
OCG_LogHandler = C.CFUNCTYPE(None, C.c_void_p, C.c_char_p, C.c_int)


class OCG_DuelOptions(C.Structure):
    _fields_ = [
        ("seed", C.c_uint64 * 4),
        ("flags", C.c_uint64),
        ("team1", OCG_Player),
        ("team2", OCG_Player),
        ("cardReader", OCG_DataReader),
        ("payload1", C.c_void_p),
        ("scriptReader", OCG_ScriptReader),
        ("payload2", C.c_void_p),
        ("logHandler", OCG_LogHandler),
        ("payload3", C.c_void_p),
        ("cardReaderDone", OCG_DataReaderDone),
        ("payload4", C.c_void_p),
        ("enableUnsafeLibraries", C.c_uint8),
    ]


class OCG_NewCardInfo(C.Structure):
    _fields_ = [
        ("team", C.c_uint8),
        ("duelist", C.c_uint8),
        ("code", C.c_uint32),
        ("con", C.c_uint8),
        ("loc", C.c_uint32),
        ("seq", C.c_uint32),
        ("pos", C.c_uint32),
    ]


class Core:
    def __init__(self, path: Path = LIB_PATH):
        if not path.exists():
            raise FileNotFoundError(f"ocgcore shared library not found: {path}")
        self.lib = C.CDLL(str(path))
        self.lib.OCG_GetVersion.argtypes = [C.POINTER(C.c_int), C.POINTER(C.c_int)]
        self.lib.OCG_GetVersion.restype = None
        self.lib.OCG_CreateDuel.argtypes = [C.POINTER(C.c_void_p), C.POINTER(OCG_DuelOptions)]
        self.lib.OCG_CreateDuel.restype = C.c_int
        self.lib.OCG_DestroyDuel.argtypes = [C.c_void_p]
        self.lib.OCG_DestroyDuel.restype = None
        self.lib.OCG_DuelNewCard.argtypes = [C.c_void_p, C.POINTER(OCG_NewCardInfo)]
        self.lib.OCG_DuelNewCard.restype = None
        self.lib.OCG_StartDuel.argtypes = [C.c_void_p]
        self.lib.OCG_StartDuel.restype = None
        self.lib.OCG_DuelProcess.argtypes = [C.c_void_p]
        self.lib.OCG_DuelProcess.restype = C.c_int
        self.lib.OCG_DuelGetMessage.argtypes = [C.c_void_p, C.POINTER(C.c_uint32)]
        self.lib.OCG_DuelGetMessage.restype = C.c_void_p
        self.lib.OCG_DuelSetResponse.argtypes = [C.c_void_p, C.c_void_p, C.c_uint32]
        self.lib.OCG_DuelSetResponse.restype = None
        self.lib.OCG_LoadScript.argtypes = [C.c_void_p, C.c_char_p, C.c_uint32, C.c_char_p]
        self.lib.OCG_LoadScript.restype = C.c_int
        self.lib.OCG_DuelQueryCount.argtypes = [C.c_void_p, C.c_uint8, C.c_uint32]
        self.lib.OCG_DuelQueryCount.restype = C.c_uint32

    def version(self) -> tuple[int, int]:
        major, minor = C.c_int(0), C.c_int(0)
        self.lib.OCG_GetVersion(C.byref(major), C.byref(minor))
        return major.value, minor.value


class CardDB:
    def __init__(self, path: Path = CDB_PATH):
        if not path.exists():
            raise FileNotFoundError(f"cards.cdb not found: {path}")
        self.con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.rows: dict[int, sqlite3.Row | None] = {}
        self.names: dict[int, str] = {}
        self.setcode_keepalive: dict[int, Any] = {}

    def row(self, code: int) -> sqlite3.Row | None:
        code = int(code)
        if code not in self.rows:
            cur = self.con.execute(
                "SELECT d.*, t.name FROM datas d LEFT JOIN texts t ON d.id=t.id WHERE d.id=?",
                (code,),
            )
            self.rows[code] = cur.fetchone()
        return self.rows[code]

    def exists(self, code: int) -> bool:
        return self.row(code) is not None

    def name(self, code: int) -> str:
        code = int(code)
        if code not in self.names:
            row = self.row(code)
            self.names[code] = str(row["name"]) if row and row["name"] else f"#{code}"
        return self.names[code]

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 50))
        rows = self.con.execute(
            "SELECT d.id, t.name FROM datas d JOIN texts t ON d.id=t.id "
            "WHERE t.name LIKE ? ORDER BY t.name LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [{"code": int(row["id"]), "name": str(row["name"])} for row in rows]

    def fill(self, code: int, data: OCG_CardData) -> None:
        C.memset(C.byref(data), 0, C.sizeof(OCG_CardData))
        row = self.row(code)
        if row is None:
            return
        u64 = 0xFFFFFFFFFFFFFFFF
        level_col = int(row["level"]) & u64
        packed_setcode = int(row["setcode"]) & u64
        codes = [(packed_setcode >> shift) & 0xFFFF for shift in (0, 16, 32, 48)]
        codes = [value for value in codes if value]
        arr = (C.c_uint16 * (len(codes) + 1))(*codes, 0)
        self.setcode_keepalive[int(code)] = arr

        ctype = int(row["type"]) & 0xFFFFFFFF
        data.code = int(code)
        data.alias = int(row["alias"]) & 0xFFFFFFFF
        data.setcodes = C.cast(arr, C.POINTER(C.c_uint16))
        data.type = ctype
        data.level = level_col & 0xFF
        data.lscale = (level_col >> 24) & 0xFF
        data.rscale = (level_col >> 16) & 0xFF
        data.attribute = int(row["attribute"]) & 0xFFFFFFFF
        data.race = int(row["race"]) & u64
        data.attack = int(row["atk"])
        if ctype & TYPE_LINK:
            data.defense = 0
            data.link_marker = int(row["def"]) & 0xFFFFFFFF
        else:
            data.defense = int(row["def"])
            data.link_marker = 0


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def _read(self, fmt: str) -> int:
        size = struct.calcsize(fmt)
        if self.pos + size > len(self.data):
            raise ValueError("message payload ended unexpectedly")
        value = struct.unpack_from(fmt, self.data, self.pos)[0]
        self.pos += size
        return int(value)

    def u8(self) -> int:
        return self._read("<B")

    def u16(self) -> int:
        return self._read("<H")

    def u32(self) -> int:
        return self._read("<I")

    def u64(self) -> int:
        return self._read("<Q")

    def bytes(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise ValueError("message payload ended unexpectedly")
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out


def i32(value: int) -> bytes:
    return struct.pack("<i", int(value))


def card_response(indices: list[int]) -> bytes:
    return i32(0) + struct.pack("<I", len(indices)) + b"".join(
        struct.pack("<I", int(index)) for index in indices
    )


def option_dict(kind: str, label: str, response: bytes, code: int = 0) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": label,
        "code": int(code),
        "_response_hex": response.hex(),
    }


class DuelBridge:
    def __init__(
        self,
        core: Core,
        db: CardDB,
        main: list[int],
        extra: list[int],
        opening_hand: list[int] | None = None,
        opponent_main: list[int] | None = None,
        opponent_extra: list[int] | None = None,
        opponent_opening_hand: list[int] | None = None,
        seed: int = 1,
    ):
        self.core = core
        self.db = db
        self.main = [int(x) for x in main]
        self.extra = [int(x) for x in extra]
        self.opening_hand = [int(x) for x in (opening_hand or [])]
        self.opponent_main = [int(x) for x in (opponent_main or [DUMMY_OPPONENT] * 40)]
        self.opponent_extra = [int(x) for x in (opponent_extra or [])]
        self.opponent_opening_hand = [int(x) for x in (opponent_opening_hand or [])]
        self.seed = int(seed)
        self.duel = C.c_void_p(0)
        self.keepalive: list[Any] = []
        self.script_cache: dict[str, bytes] = {}
        self.errors: list[str] = []
        self._create()
        self._setup()

    def _card_reader(self):
        def reader(_payload, code, data_ptr):
            self.db.fill(int(code), data_ptr[0])

        callback = OCG_DataReader(reader)
        self.keepalive.append(callback)
        return callback

    def _script_reader(self):
        def reader(_payload, _duel, name_bytes):
            name = name_bytes.decode("utf-8", "replace")
            content = self._read_script(name)
            if content is None:
                self.errors.append(f"missing script: {name}")
                return 0
            return self.core.lib.OCG_LoadScript(self.duel, content, len(content), name_bytes)

        callback = OCG_ScriptReader(reader)
        self.keepalive.append(callback)
        return callback

    def _log_handler(self):
        def handler(_payload, msg, mtype):
            text = msg.decode("utf-8", "replace") if msg else ""
            if text:
                self.errors.append(f"log[{int(mtype)}]: {text}")

        callback = OCG_LogHandler(handler)
        self.keepalive.append(callback)
        return callback

    def _read_script(self, name: str) -> bytes | None:
        if name in self.script_cache:
            return self.script_cache[name]
        for candidate in (SCRIPTS / "official" / name, SCRIPTS / name):
            if candidate.exists():
                data = candidate.read_bytes()
                self.script_cache[name] = data
                return data
        return None

    def _create(self):
        opts = OCG_DuelOptions()
        rng = random.Random(self.seed)
        for index in range(4):
            opts.seed[index] = rng.getrandbits(64)
        opts.flags = DUEL_MODE_MR5 | DUEL_PSEUDO_SHUFFLE
        for team in (opts.team1, opts.team2):
            team.startingLP = 8000
            team.startingDrawCount = 5
            team.drawCountPerTurn = 1
        opts.cardReader = self._card_reader()
        opts.scriptReader = self._script_reader()
        opts.logHandler = self._log_handler()
        opts.cardReaderDone = OCG_DataReaderDone(0)
        opts.enableUnsafeLibraries = 0

        status = self.core.lib.OCG_CreateDuel(C.byref(self.duel), C.byref(opts))
        if status != OCG_DUEL_CREATION_SUCCESS:
            raise RuntimeError(f"OCG_CreateDuel failed with status {status}")

        for script in ("constant.lua", "utility.lua"):
            content = self._read_script(script)
            if content is None:
                raise RuntimeError(f"required script missing: {script}")
            ok = self.core.lib.OCG_LoadScript(self.duel, content, len(content), script.encode())
            if ok != 1:
                raise RuntimeError(f"failed to preload {script}: {self.errors[-5:]}")

    def _new_card(self, code: int, player: int, location: int):
        info = OCG_NewCardInfo()
        info.team = int(player)
        info.duelist = 0
        info.code = int(code)
        info.con = int(player)
        info.loc = int(location)
        info.seq = 0
        info.pos = 0
        self.core.lib.OCG_DuelNewCard(self.duel, C.byref(info))

    def _load_deck(
        self,
        player: int,
        main: list[int],
        extra: list[int],
        opening_hand: list[int] | None = None,
    ):
        ordered = list(main)
        if opening_hand:
            remaining = list(main)
            for code in opening_hand:
                try:
                    remaining.remove(code)
                except ValueError as exc:
                    raise ValueError(
                        f"opening hand card {code} is not present enough times in main deck"
                    ) from exc
            ordered = remaining + list(opening_hand)
        for code in ordered:
            self._new_card(code, player, LOCATION_DECK)
        for code in extra:
            self._new_card(code, player, LOCATION_EXTRA)

    def _setup(self):
        self._load_deck(0, self.main, self.extra, self.opening_hand or None)
        self._load_deck(
            1,
            self.opponent_main,
            self.opponent_extra,
            self.opponent_opening_hand or None,
        )
        self.core.lib.OCG_StartDuel(self.duel)

    def close(self):
        if self.duel:
            self.core.lib.OCG_DestroyDuel(self.duel)
            self.duel = C.c_void_p(0)

    def set_response(self, response: bytes):
        if not response:
            buf = (C.c_ubyte * 1)(0)
            self.core.lib.OCG_DuelSetResponse(self.duel, buf, 0)
            return
        buf = (C.c_ubyte * len(response)).from_buffer_copy(response)
        self.core.lib.OCG_DuelSetResponse(self.duel, buf, len(response))

    def process_once(self) -> tuple[int, list[tuple[int, bytes]]]:
        status = int(self.core.lib.OCG_DuelProcess(self.duel))
        length = C.c_uint32(0)
        ptr = self.core.lib.OCG_DuelGetMessage(self.duel, C.byref(length))
        messages: list[tuple[int, bytes]] = []
        if ptr and length.value:
            raw = C.string_at(ptr, length.value)
            reader = Reader(raw)
            while reader.pos + 4 <= len(raw):
                size = reader.u32()
                body = reader.bytes(size)
                if body:
                    messages.append((body[0], body[1:]))
        return status, messages

    def counts(self, player: int = 0) -> dict[str, int]:
        query = self.core.lib.OCG_DuelQueryCount
        player = int(player)
        return {
            "deck": int(query(self.duel, player, LOCATION_DECK)),
            "hand": int(query(self.duel, player, LOCATION_HAND)),
            "monster_zone": int(query(self.duel, player, LOCATION_MZONE)),
            "spell_trap_zone": int(query(self.duel, player, LOCATION_SZONE)),
            "graveyard": int(query(self.duel, player, LOCATION_GRAVE)),
            "banished": int(query(self.duel, player, LOCATION_REMOVED)),
            "extra": int(query(self.duel, player, LOCATION_EXTRA)),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "player": self.counts(0),
            "opponent": self.counts(1),
        }

    def parse_branch(self, mtype: int, payload: bytes) -> dict[str, Any] | None:
        try:
            if mtype == MSG_SELECT_IDLECMD:
                return self._parse_idle(payload)
            if mtype == MSG_SELECT_BATTLECMD:
                return self._parse_battle(payload)
            if mtype == MSG_SELECT_CHAIN:
                return self._parse_chain(payload)
            if mtype == MSG_SELECT_OPTION:
                return self._parse_option(payload)
            if mtype in (MSG_SELECT_EFFECTYN, MSG_SELECT_YESNO):
                return self._parse_yesno(mtype, payload)
            if mtype == MSG_SELECT_CARD:
                return self._parse_single_card(payload)
            if mtype == MSG_SELECT_POSITION:
                return self._parse_position(payload)
        except Exception as exc:
            self.errors.append(f"parse {MSG_NAMES.get(mtype, mtype)} failed: {exc}")
        return None

    def _parse_idle(self, payload: bytes) -> dict[str, Any]:
        reader = Reader(payload)
        player = reader.u8()
        options: list[dict[str, Any]] = []

        def simple(kind: str, cmd: int, seq8: bool = False, activate: bool = False):
            count = reader.u32()
            for index in range(count):
                code = reader.u32()
                reader.u8()
                reader.u8()
                if seq8:
                    reader.u8()
                else:
                    reader.u32()
                if activate:
                    reader.u64()
                    reader.u8()
                labels = {
                    "summon": "Normal Summon",
                    "spsummon": "Special Summon",
                    "repos": "Reposition",
                    "mset": "Set Monster",
                    "set": "Set Spell/Trap",
                    "activate": "Activate",
                }
                options.append(
                    option_dict(
                        kind,
                        f"{labels[kind]}: {self.db.name(code)}",
                        i32((index << 16) | cmd),
                        code,
                    )
                )

        simple("summon", IDLE_SUMMON)
        simple("spsummon", IDLE_SPSUMMON)
        simple("repos", IDLE_REPOS, seq8=True)
        simple("mset", IDLE_MSET)
        simple("set", IDLE_SSET)
        simple("activate", IDLE_ACTIVATE, activate=True)
        can_battle = reader.u8()
        can_end = reader.u8()
        reader.u8()
        if can_battle:
            options.append(option_dict("battle", "Enter Battle Phase", i32(IDLE_TO_BP)))
        if can_end:
            options.append(option_dict("end", "End Phase", i32(IDLE_TO_EP)))
        return {"message": "MSG_SELECT_IDLECMD", "player": player, "options": options}

    def _parse_battle(self, payload: bytes) -> dict[str, Any]:
        reader = Reader(payload)
        player = reader.u8()
        options: list[dict[str, Any]] = []

        count = reader.u32()
        for index in range(count):
            code = reader.u32()
            reader.u8()
            reader.u8()
            reader.u32()
            reader.u64()
            reader.u8()
            options.append(
                option_dict(
                    "battle_activate",
                    f"Battle Activate: {self.db.name(code)}",
                    i32((index << 16) | BATTLE_ACTIVATE),
                    code,
                )
            )

        count = reader.u32()
        for index in range(count):
            code = reader.u32()
            reader.u8()
            reader.u8()
            reader.u8()
            reader.u8()
            options.append(
                option_dict(
                    "attack",
                    f"Attack: {self.db.name(code)}",
                    i32((index << 16) | BATTLE_ATTACK),
                    code,
                )
            )

        can_m2 = reader.u8()
        can_ep = reader.u8()
        if can_m2:
            options.append(
                option_dict("main2", "Enter Main Phase 2", i32(BATTLE_TO_M2))
            )
        if can_ep:
            options.append(option_dict("end", "End Phase", i32(BATTLE_TO_EP)))
        return {"message": "MSG_SELECT_BATTLECMD", "player": player, "options": options}

    def _parse_chain(self, payload: bytes) -> dict[str, Any]:
        reader = Reader(payload)
        player = reader.u8()
        reader.u8()
        forced = reader.u8()
        reader.u32()
        reader.u32()
        count = reader.u32()
        options: list[dict[str, Any]] = []
        for index in range(count):
            code = reader.u32()
            reader.u8()
            reader.u8()
            reader.u32()
            reader.u32()
            reader.u64()
            reader.u8()
            options.append(
                option_dict("chain", f"Chain: {self.db.name(code)}", i32(index), code)
            )
        if not forced:
            options.append(option_dict("decline", "No response", i32(-1)))
        return {"message": "MSG_SELECT_CHAIN", "player": player, "options": options}

    def _parse_option(self, payload: bytes) -> dict[str, Any]:
        reader = Reader(payload)
        player = reader.u8()
        count = reader.u8()
        options = [
            option_dict("option", f"Option {index + 1}", i32(index))
            for index in range(count)
        ]
        return {"message": "MSG_SELECT_OPTION", "player": player, "options": options}

    def _parse_yesno(self, mtype: int, payload: bytes) -> dict[str, Any]:
        reader = Reader(payload)
        player = reader.u8()
        code = 0
        if mtype == MSG_SELECT_EFFECTYN:
            code = reader.u32()
        options = [
            option_dict("yes", "Yes", i32(1), code),
            option_dict("no", "No", i32(0), code),
        ]
        return {"message": MSG_NAMES[mtype], "player": player, "options": options}

    def _parse_single_card(self, payload: bytes) -> dict[str, Any] | None:
        reader = Reader(payload)
        player = reader.u8()
        reader.u8()
        minimum = reader.u32()
        maximum = reader.u32()
        count = reader.u32()
        if maximum != 1 or count <= 1:
            return None
        options: list[dict[str, Any]] = []
        for index in range(count):
            code = reader.u32()
            reader.u8()
            reader.u8()
            reader.u32()
            reader.u32()
            options.append(
                option_dict(
                    "select_card",
                    f"Choose: {self.db.name(code)}",
                    card_response([index]),
                    code,
                )
            )
        if minimum == 0:
            options.append(option_dict("decline", "Choose none", card_response([])))
        return {"message": "MSG_SELECT_CARD", "player": player, "options": options}

    def _parse_position(self, payload: bytes) -> dict[str, Any] | None:
        reader = Reader(payload)
        player = reader.u8()
        code = reader.u32()
        positions = reader.u8()
        candidates = [
            (POS_FACEUP_ATTACK, "Face-up Attack"),
            (POS_FACEUP_DEFENSE, "Face-up Defense"),
            (POS_FACEDOWN_DEFENSE, "Face-down Defense"),
            (POS_FACEDOWN_ATTACK, "Face-down Attack"),
        ]
        available = [(pos, label) for pos, label in candidates if positions & pos]
        if len(available) <= 1:
            return None
        options = [
            option_dict("position", label, i32(pos), code)
            for pos, label in available
        ]
        return {"message": "MSG_SELECT_POSITION", "player": player, "options": options}

    def default_response(self, mtype: int, payload: bytes) -> bytes | None:
        try:
            reader = Reader(payload)
            if mtype in (MSG_SELECT_CARD, MSG_SELECT_TRIBUTE):
                reader.u8()
                reader.u8()
                minimum = reader.u32()
                return card_response(list(range(minimum)))
            if mtype in (MSG_SELECT_PLACE, MSG_SELECT_DISFIELD):
                player = reader.u8()
                count = reader.u8()
                flag = reader.u32()
                candidates: list[tuple[int, int, int]] = []
                for seq in range(7):
                    if not (flag & (1 << seq)):
                        candidates.append((player, LOCATION_MZONE, seq))
                for seq in range(8):
                    if not (flag & (1 << (8 + seq))):
                        candidates.append((player, LOCATION_SZONE, seq))
                other = 1 - player
                for seq in range(7):
                    if not (flag & (1 << (16 + seq))):
                        candidates.append((other, LOCATION_MZONE, seq))
                for seq in range(8):
                    if not (flag & (1 << (24 + seq))):
                        candidates.append((other, LOCATION_SZONE, seq))
                if len(candidates) < count:
                    return None
                out = bytearray()
                for select_player, location, sequence in candidates[:count]:
                    out.extend(bytes((select_player, location, sequence)))
                return bytes(out)
            if mtype == MSG_SELECT_POSITION:
                reader.u8()
                reader.u32()
                positions = reader.u8()
                for pos in (
                    POS_FACEUP_ATTACK,
                    POS_FACEUP_DEFENSE,
                    POS_FACEDOWN_DEFENSE,
                    POS_FACEDOWN_ATTACK,
                ):
                    if positions & pos:
                        return i32(pos)
                return None
            if mtype == MSG_SELECT_UNSELECT_CARD:
                reader.u8()
                finishable = reader.u8()
                reader.u8()
                if finishable:
                    return i32(-1)
                return i32(1) + i32(0)
            if mtype in (MSG_SORT_CARD, MSG_SORT_CHAIN):
                return b"\xff"
            if mtype == MSG_SELECT_BATTLECMD:
                return i32(3)
            if mtype == MSG_ROCK_PAPER_SCISSORS:
                return i32(1)
            if mtype == MSG_ANNOUNCE_NUMBER:
                return i32(0)
            if mtype == MSG_SELECT_COUNTER:
                reader.u8()
                reader.u16()
                needed = reader.u16()
                card_count = reader.u32()
                available: list[int] = []
                for _ in range(card_count):
                    reader.u32()
                    reader.u8()
                    reader.u8()
                    reader.u8()
                    available.append(reader.u16())
                remaining = needed
                chosen: list[int] = []
                for count in available:
                    take = min(count, remaining)
                    chosen.append(take)
                    remaining -= take
                if remaining:
                    return None
                return b"".join(struct.pack("<h", count) for count in chosen)
            if mtype in (MSG_ANNOUNCE_RACE, MSG_ANNOUNCE_ATTRIB):
                reader.u8()
                count = reader.u8()
                available = reader.u64() if mtype == MSG_ANNOUNCE_RACE else reader.u32()
                selected = 0
                for bit in range(64 if mtype == MSG_ANNOUNCE_RACE else 32):
                    mask = 1 << bit
                    if available & mask:
                        selected |= mask
                        count -= 1
                        if count <= 0:
                            break
                if count > 0:
                    return None
                return struct.pack("<Q" if mtype == MSG_ANNOUNCE_RACE else "<I", selected)
            if mtype in (
                MSG_SELECT_SUM,
                MSG_ANNOUNCE_CARD,
            ):
                return None
        except Exception as exc:
            self.errors.append(
                f"default response parse failed for {MSG_NAMES.get(mtype, mtype)}: {exc}"
            )
        return None

    def replay(self, choices: list[int], max_process_steps: int = 500) -> dict[str, Any]:
        choice_cursor = 0
        action_trace: list[str] = []
        last_messages: list[str] = []

        for step in range(max_process_steps):
            status, messages = self.process_once()
            last_messages = [
                MSG_NAMES.get(message_type, f"MSG_{message_type}")
                for message_type, _ in messages[-12:]
            ]
            if any(message_type == MSG_RETRY for message_type, _ in messages):
                return {
                    "status": "retry_error",
                    "process_step": step,
                    "choices_consumed": choice_cursor,
                    "trace": action_trace,
                    "last_messages": last_messages,
                    "counts": self.counts(),
                    "errors": self.errors[-20:],
                }
            if status == OCG_DUEL_STATUS_END:
                return {
                    "status": "duel_end",
                    "process_step": step,
                    "choices_consumed": choice_cursor,
                    "trace": action_trace,
                    "last_messages": last_messages,
                    "counts": self.counts(),
                    "errors": self.errors[-20:],
                }
            if status != OCG_DUEL_STATUS_AWAITING:
                continue
            if not messages:
                return {
                    "status": "awaiting_without_message",
                    "process_step": step,
                    "choices_consumed": choice_cursor,
                    "trace": action_trace,
                    "counts": self.counts(),
                    "errors": self.errors[-20:],
                }

            message_type, payload = messages[-1]
            branch = self.parse_branch(message_type, payload)
            if branch and branch["options"]:
                if choice_cursor >= len(choices):
                    public_options = [
                        {key: value for key, value in option.items() if not key.startswith("_")}
                        for option in branch["options"]
                    ]
                    return {
                        "status": "awaiting_choice",
                        "process_step": step,
                        "choices_consumed": choice_cursor,
                        "trace": action_trace,
                        "decision": {
                            "message": branch["message"],
                            "player": branch["player"],
                            "options": public_options,
                        },
                        "last_messages": last_messages,
                        "counts": self.counts(),
                        "errors": self.errors[-20:],
                    }
                selected = int(choices[choice_cursor])
                if selected < 0 or selected >= len(branch["options"]):
                    return {
                        "status": "invalid_choice",
                        "process_step": step,
                        "choices_consumed": choice_cursor,
                        "provided_choice": selected,
                        "available_count": len(branch["options"]),
                        "trace": action_trace,
                        "counts": self.counts(),
                    }
                option = branch["options"][selected]
                action_trace.append(option["label"])
                choice_cursor += 1
                self.set_response(bytes.fromhex(option["_response_hex"]))
                continue

            automatic = self.default_response(message_type, payload)
            if automatic is None:
                return {
                    "status": "unsupported_prompt",
                    "process_step": step,
                    "choices_consumed": choice_cursor,
                    "trace": action_trace,
                    "message": MSG_NAMES.get(message_type, f"MSG_{message_type}"),
                    "raw_payload_hex": payload.hex(),
                    "last_messages": last_messages,
                    "counts": self.counts(),
                    "errors": self.errors[-20:],
                }
            self.set_response(automatic)

        return {
            "status": "process_budget_exhausted",
            "process_steps": max_process_steps,
            "choices_consumed": choice_cursor,
            "trace": action_trace,
            "last_messages": last_messages,
            "counts": self.counts(),
            "errors": self.errors[-20:],
        }


    def _public_options(self, branch: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {key: value for key, value in option.items() if not key.startswith("_")}
            for option in branch.get("options", [])
        ]

    def _choose_opponent_option(
        self,
        branch: dict[str, Any],
        handtrap_priority: list[int],
        target_priority: list[int],
    ) -> int:
        options = branch.get("options", [])
        message = str(branch.get("message", ""))
        if not options:
            return 0

        if message == "MSG_SELECT_CHAIN":
            for wanted in handtrap_priority:
                for index, option in enumerate(options):
                    if option.get("kind") == "chain" and int(option.get("code", 0)) == wanted:
                        return index
            for index, option in enumerate(options):
                if option.get("kind") == "decline":
                    return index
            return 0

        if message in {"MSG_SELECT_EFFECTYN", "MSG_SELECT_YESNO"}:
            for index, option in enumerate(options):
                if option.get("kind") == "yes":
                    return index

        if message == "MSG_SELECT_CARD":
            for wanted in target_priority:
                for index, option in enumerate(options):
                    if int(option.get("code", 0)) == wanted:
                        return index
            return 0

        if message == "MSG_SELECT_IDLECMD":
            for index, option in enumerate(options):
                if option.get("kind") == "end":
                    return index
            return 0

        return 0

    def _choose_candidate_option(self, branch: dict[str, Any]) -> int:
        options = branch.get("options", [])
        message = str(branch.get("message", ""))
        if not options:
            return 0

        if message == "MSG_SELECT_IDLECMD":
            priority = {
                "activate": 0,
                "spsummon": 1,
                "summon": 2,
                "repos": 3,
                "mset": 4,
                "set": 5,
                "battle": 8,
                "end": 9,
            }
            return min(
                range(len(options)),
                key=lambda index: (
                    priority.get(str(options[index].get("kind", "")), 7),
                    index,
                ),
            )

        if message == "MSG_SELECT_CHAIN":
            for index, option in enumerate(options):
                if option.get("kind") == "chain":
                    return index
            for index, option in enumerate(options):
                if option.get("kind") == "decline":
                    return index

        if message in {"MSG_SELECT_EFFECTYN", "MSG_SELECT_YESNO"}:
            for index, option in enumerate(options):
                if option.get("kind") == "yes":
                    return index

        return 0

    def _choose_autoplay_option(
        self,
        branch: dict[str, Any],
        *,
        profile: str,
        reaction_priority: list[int],
        target_priority: list[int],
        reaction_hold_windows: dict[int, int],
        reaction_min_opponent_summons: dict[int, int],
        reaction_windows_seen: Counter[int],
        summons_this_turn: list[int],
    ) -> int:
        options = branch.get("options", [])
        message = str(branch.get("message", ""))
        player = int(branch.get("player", 0))
        if not options:
            return 0

        if message == "MSG_SELECT_CHAIN":
            decline_index = next(
                (index for index, option in enumerate(options) if option.get("kind") == "decline"),
                None,
            )
            for wanted in reaction_priority:
                for index, option in enumerate(options):
                    if option.get("kind") != "chain" or int(option.get("code", 0)) != wanted:
                        continue
                    reaction_windows_seen[wanted] += 1
                    hold = max(0, int(reaction_hold_windows.get(wanted, 0)))
                    min_summons = max(
                        0,
                        int(reaction_min_opponent_summons.get(wanted, 0)),
                    )
                    opponent = 1 - player
                    if (
                        reaction_windows_seen[wanted] > hold
                        and summons_this_turn[opponent] >= min_summons
                    ):
                        return index

            non_reaction = [
                (index, option)
                for index, option in enumerate(options)
                if option.get("kind") == "chain"
                and int(option.get("code", 0)) not in set(reaction_priority)
            ]
            if non_reaction and profile != "passive":
                return non_reaction[0][0]
            if decline_index is not None:
                return decline_index
            return 0

        if message == "MSG_SELECT_IDLECMD":
            if profile == "control":
                order = {
                    "activate": 0,
                    "set": 1,
                    "mset": 2,
                    "spsummon": 3,
                    "summon": 4,
                    "repos": 5,
                    "battle": 7,
                    "end": 8,
                }
            elif profile == "aggressive":
                order = {
                    "activate": 0,
                    "spsummon": 1,
                    "summon": 2,
                    "battle": 3,
                    "repos": 4,
                    "set": 5,
                    "mset": 6,
                    "end": 9,
                }
            elif profile == "passive":
                order = {
                    "end": 0,
                    "set": 1,
                    "mset": 2,
                    "repos": 3,
                    "summon": 7,
                    "spsummon": 8,
                    "activate": 9,
                    "battle": 9,
                }
            else:
                order = {
                    "activate": 0,
                    "spsummon": 1,
                    "summon": 2,
                    "set": 3,
                    "mset": 4,
                    "repos": 5,
                    "battle": 7,
                    "end": 8,
                }
            return min(
                range(len(options)),
                key=lambda index: (
                    order.get(str(options[index].get("kind", "")), 6),
                    index,
                ),
            )

        if message == "MSG_SELECT_BATTLECMD":
            order = {
                "battle_activate": 0,
                "attack": 1,
                "main2": 2,
                "end": 3,
            }
            return min(
                range(len(options)),
                key=lambda index: (
                    order.get(str(options[index].get("kind", "")), 4),
                    index,
                ),
            )

        if message in {"MSG_SELECT_EFFECTYN", "MSG_SELECT_YESNO"}:
            for index, option in enumerate(options):
                if option.get("kind") == "yes":
                    return index

        if message == "MSG_SELECT_CARD":
            for wanted in target_priority:
                for index, option in enumerate(options):
                    if int(option.get("code", 0)) == wanted:
                        return index

        if message == "MSG_SELECT_POSITION":
            for index, option in enumerate(options):
                if option.get("label") == "Face-up Attack":
                    return index

        return 0

    def autoplay(
        self,
        *,
        profiles: tuple[str, str] = ("balanced", "balanced"),
        reaction_priorities: tuple[list[int], list[int]] = ([], []),
        target_priorities: tuple[list[int], list[int]] = ([], []),
        reaction_hold_windows: tuple[dict[int, int], dict[int, int]] = ({}, {}),
        reaction_min_opponent_summons: tuple[dict[int, int], dict[int, int]] = ({}, {}),
        max_decisions: int = 600,
        max_process_steps: int = 6000,
        stop_after_turns: int = 0,
    ) -> dict[str, Any]:
        profiles = tuple(
            profile if profile in {"balanced", "aggressive", "control", "passive"}
            else "balanced"
            for profile in profiles
        )
        action_trace: list[dict[str, Any]] = []
        reaction_windows_seen = (Counter(), Counter())
        summons_this_turn = [0, 0]
        turn_count = 0
        turn_player: int | None = None
        phase: int | None = None
        winner: int | None = None
        win_reason: int | None = None
        decisions = 0
        last_messages: list[str] = []

        for step in range(max_process_steps):
            status, messages = self.process_once()
            last_messages = [
                MSG_NAMES.get(message_type, f"MSG_{message_type}")
                for message_type, _ in messages[-12:]
            ]

            for message_type, payload in messages:
                if message_type == MSG_WIN and len(payload) >= 2:
                    winner = int(payload[0])
                    win_reason = int(payload[1])
                elif message_type == MSG_NEW_TURN and payload:
                    turn_player = int(payload[0])
                    turn_count += 1
                    summons_this_turn = [0, 0]
                elif message_type == MSG_NEW_PHASE and len(payload) >= 2:
                    phase = int(struct.unpack_from("<H", payload, 0)[0])
                elif message_type in (
                    MSG_SUMMONING,
                    MSG_SPSUMMONING,
                    MSG_FLIPSUMMONING,
                ) and len(payload) >= 5:
                    controller = int(payload[4])
                    if controller in (0, 1):
                        summons_this_turn[controller] += 1

            if winner is not None:
                return {
                    "status": "duel_end",
                    "winner": winner,
                    "win_reason": win_reason,
                    "turn_count": turn_count,
                    "turn_player": turn_player,
                    "phase": phase,
                    "decisions": decisions,
                    "summons_this_turn": summons_this_turn,
                    "trace": action_trace[-240:],
                    "counts": self.counts(0),
                    "opponent_counts": self.counts(1),
                    "errors": self.errors[-20:],
                }

            if stop_after_turns > 0 and turn_count > stop_after_turns:
                return {
                    "status": "turn_limit_reached",
                    "winner": None,
                    "win_reason": None,
                    "turn_count": turn_count,
                    "turn_player": turn_player,
                    "phase": phase,
                    "decisions": decisions,
                    "summons_this_turn": summons_this_turn,
                    "trace": action_trace[-240:],
                    "counts": self.counts(0),
                    "opponent_counts": self.counts(1),
                    "errors": self.errors[-20:],
                }

            if any(message_type == MSG_RETRY for message_type, _ in messages):
                return {
                    "status": "retry_error",
                    "winner": None,
                    "turn_count": turn_count,
                    "decisions": decisions,
                    "trace": action_trace[-240:],
                    "counts": self.counts(0),
                    "opponent_counts": self.counts(1),
                    "errors": self.errors[-20:],
                }
            if status == OCG_DUEL_STATUS_END:
                return {
                    "status": "duel_end_no_winner_message",
                    "winner": winner,
                    "win_reason": win_reason,
                    "turn_count": turn_count,
                    "decisions": decisions,
                    "trace": action_trace[-240:],
                    "counts": self.counts(0),
                    "opponent_counts": self.counts(1),
                    "errors": self.errors[-20:],
                }
            if status != OCG_DUEL_STATUS_AWAITING:
                continue
            if not messages:
                return {
                    "status": "awaiting_without_message",
                    "winner": None,
                    "turn_count": turn_count,
                    "decisions": decisions,
                    "trace": action_trace[-240:],
                    "counts": self.counts(0),
                    "opponent_counts": self.counts(1),
                    "errors": self.errors[-20:],
                }

            message_type, payload = messages[-1]
            branch = self.parse_branch(message_type, payload)
            if branch and branch.get("options"):
                player = int(branch.get("player", 0))
                options = branch["options"]
                selected = self._choose_autoplay_option(
                    branch,
                    profile=profiles[player],
                    reaction_priority=reaction_priorities[player],
                    target_priority=target_priorities[player],
                    reaction_hold_windows=reaction_hold_windows[player],
                    reaction_min_opponent_summons=reaction_min_opponent_summons[player],
                    reaction_windows_seen=reaction_windows_seen[player],
                    summons_this_turn=summons_this_turn,
                )
                selected = max(0, min(int(selected), len(options) - 1))
                option = options[selected]
                action_trace.append(
                    {
                        "decision": decisions + 1,
                        "turn": turn_count,
                        "phase": phase,
                        "player": player,
                        "message": branch.get("message"),
                        "option_index": selected,
                        "kind": option.get("kind"),
                        "label": option.get("label"),
                        "code": int(option.get("code", 0)),
                        "summons_this_turn": list(summons_this_turn),
                    }
                )
                decisions += 1
                if decisions >= max_decisions:
                    return {
                        "status": "decision_budget_exhausted",
                        "winner": None,
                        "turn_count": turn_count,
                        "decisions": decisions,
                        "trace": action_trace[-240:],
                        "counts": self.counts(0),
                        "opponent_counts": self.counts(1),
                        "errors": self.errors[-20:],
                    }
                self.set_response(bytes.fromhex(option["_response_hex"]))
                continue

            automatic = self.default_response(message_type, payload)
            if automatic is None:
                return {
                    "status": "unsupported_prompt",
                    "winner": None,
                    "turn_count": turn_count,
                    "decisions": decisions,
                    "message": MSG_NAMES.get(message_type, f"MSG_{message_type}"),
                    "raw_payload_hex": payload.hex(),
                    "trace": action_trace[-240:],
                    "counts": self.counts(0),
                    "opponent_counts": self.counts(1),
                    "errors": self.errors[-20:],
                }
            self.set_response(automatic)

        return {
            "status": "process_budget_exhausted",
            "winner": None,
            "turn_count": turn_count,
            "decisions": decisions,
            "last_messages": last_messages,
            "trace": action_trace[-240:],
            "counts": self.counts(0),
            "opponent_counts": self.counts(1),
            "errors": self.errors[-20:],
        }

    def replay_policy(
        self,
        player_choices: list[int] | None = None,
        *,
        opponent_handtrap_codes: list[int] | None = None,
        opponent_target_priority: list[int] | None = None,
        auto_player: bool = False,
        max_player_decisions: int = 80,
        max_process_steps: int = 1200,
    ) -> dict[str, Any]:
        player_choices = [int(value) for value in (player_choices or [])]
        handtrap_priority = [int(value) for value in (opponent_handtrap_codes or [])]
        target_priority = [int(value) for value in (opponent_target_priority or [])]
        choice_cursor = 0
        candidate_decisions = 0
        action_trace: list[dict[str, Any]] = []
        handtraps_used: list[dict[str, Any]] = []
        last_messages: list[str] = []

        for step in range(max_process_steps):
            status, messages = self.process_once()
            last_messages = [
                MSG_NAMES.get(message_type, f"MSG_{message_type}")
                for message_type, _ in messages[-12:]
            ]
            if any(message_type == MSG_RETRY for message_type, _ in messages):
                return {
                    "status": "retry_error",
                    "process_step": step,
                    "choices_consumed": choice_cursor,
                    "trace": action_trace,
                    "handtraps_used": handtraps_used,
                    "last_messages": last_messages,
                    "counts": self.counts(0),
                    "opponent_counts": self.counts(1),
                    "errors": self.errors[-20:],
                }
            if status == OCG_DUEL_STATUS_END:
                return {
                    "status": "duel_end",
                    "process_step": step,
                    "choices_consumed": choice_cursor,
                    "trace": action_trace,
                    "handtraps_used": handtraps_used,
                    "last_messages": last_messages,
                    "counts": self.counts(0),
                    "opponent_counts": self.counts(1),
                    "errors": self.errors[-20:],
                }
            if status != OCG_DUEL_STATUS_AWAITING:
                continue
            if not messages:
                return {
                    "status": "awaiting_without_message",
                    "process_step": step,
                    "choices_consumed": choice_cursor,
                    "trace": action_trace,
                    "handtraps_used": handtraps_used,
                    "counts": self.counts(0),
                    "opponent_counts": self.counts(1),
                    "errors": self.errors[-20:],
                }

            message_type, payload = messages[-1]
            branch = self.parse_branch(message_type, payload)
            if branch and branch.get("options"):
                player = int(branch.get("player", 0))
                options = branch["options"]

                if player == 1:
                    selected = self._choose_opponent_option(
                        branch,
                        handtrap_priority,
                        target_priority,
                    )
                    selected = max(0, min(int(selected), len(options) - 1))
                    option = options[selected]
                    trace_row = {
                        "player": 1,
                        "message": branch.get("message"),
                        "option_index": selected,
                        "kind": option.get("kind"),
                        "label": option.get("label"),
                        "code": int(option.get("code", 0)),
                    }
                    action_trace.append(trace_row)
                    if (
                        option.get("kind") == "chain"
                        and int(option.get("code", 0)) in handtrap_priority
                    ):
                        handtraps_used.append(trace_row)
                    self.set_response(bytes.fromhex(option["_response_hex"]))
                    continue

                if candidate_decisions >= max_player_decisions:
                    return {
                        "status": "player_decision_budget_exhausted",
                        "process_step": step,
                        "choices_consumed": choice_cursor,
                        "trace": action_trace,
                        "handtraps_used": handtraps_used,
                        "decision": {
                            "message": branch["message"],
                            "player": player,
                            "options": self._public_options(branch),
                        },
                        "counts": self.counts(0),
                        "opponent_counts": self.counts(1),
                        "errors": self.errors[-20:],
                    }

                if choice_cursor < len(player_choices):
                    selected = int(player_choices[choice_cursor])
                    choice_cursor += 1
                elif auto_player:
                    selected = self._choose_candidate_option(branch)
                else:
                    return {
                        "status": "awaiting_choice",
                        "process_step": step,
                        "choices_consumed": choice_cursor,
                        "trace": action_trace,
                        "handtraps_used": handtraps_used,
                        "decision": {
                            "message": branch["message"],
                            "player": player,
                            "options": self._public_options(branch),
                        },
                        "last_messages": last_messages,
                        "counts": self.counts(0),
                        "opponent_counts": self.counts(1),
                        "errors": self.errors[-20:],
                    }

                if selected < 0 or selected >= len(options):
                    return {
                        "status": "invalid_choice",
                        "process_step": step,
                        "choices_consumed": choice_cursor,
                        "provided_choice": selected,
                        "available_count": len(options),
                        "trace": action_trace,
                        "counts": self.counts(0),
                        "opponent_counts": self.counts(1),
                    }

                option = options[selected]
                action_trace.append(
                    {
                        "player": 0,
                        "message": branch.get("message"),
                        "option_index": selected,
                        "kind": option.get("kind"),
                        "label": option.get("label"),
                        "code": int(option.get("code", 0)),
                    }
                )
                candidate_decisions += 1
                self.set_response(bytes.fromhex(option["_response_hex"]))
                continue

            automatic = self.default_response(message_type, payload)
            if automatic is None:
                return {
                    "status": "unsupported_prompt",
                    "process_step": step,
                    "choices_consumed": choice_cursor,
                    "trace": action_trace,
                    "handtraps_used": handtraps_used,
                    "message": MSG_NAMES.get(message_type, f"MSG_{message_type}"),
                    "raw_payload_hex": payload.hex(),
                    "last_messages": last_messages,
                    "counts": self.counts(0),
                    "opponent_counts": self.counts(1),
                    "errors": self.errors[-20:],
                }
            self.set_response(automatic)

        return {
            "status": "process_budget_exhausted",
            "process_steps": max_process_steps,
            "choices_consumed": choice_cursor,
            "trace": action_trace,
            "handtraps_used": handtraps_used,
            "last_messages": last_messages,
            "counts": self.counts(0),
            "opponent_counts": self.counts(1),
            "errors": self.errors[-20:],
        }


_core_singleton: Core | None = None
_db_singleton: CardDB | None = None


def get_core() -> Core:
    global _core_singleton
    if _core_singleton is None:
        _core_singleton = Core()
    return _core_singleton


def get_db() -> CardDB:
    global _db_singleton
    if _db_singleton is None:
        _db_singleton = CardDB()
    return _db_singleton


def clean_codes(values: list[int] | None) -> list[int]:
    return [int(value) for value in (values or [])]


def validate_input_deck(
    main: list[int],
    extra: list[int],
    side: list[int] | None = None,
) -> dict[str, Any]:
    db = get_db()
    side_codes = clean_codes(side)
    all_codes = list(main) + list(extra) + side_codes
    missing = sorted({code for code in all_codes if not db.exists(code)})
    copies = Counter(all_codes)
    copy_warnings = [
        {"code": code, "name": db.name(code), "copies": count}
        for code, count in copies.items()
        if count > 3
    ]
    return {
        "ok_for_simulation": (
            not missing
            and 1 <= len(main) <= 60
            and len(extra) <= 15
            and len(side_codes) <= 15
        ),
        "main_count": len(main),
        "extra_count": len(extra),
        "side_count": len(side_codes),
        "missing_codes": missing,
        "copy_count_warnings": copy_warnings,
        "notes": [
            "This structural validator does not apply an OCG Limit Regulation list yet.",
            "The simulation layer uses Master Rule 5 OCG flags and does not enable TCG-only SEGOC flags.",
        ],
    }


def normalize_int_map(values: dict[str, int] | None) -> dict[int, int]:
    out: dict[int, int] = {}
    for key, value in (values or {}).items():
        try:
            out[int(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return out


def runtime_fingerprint() -> dict[str, Any]:
    try:
        return json.loads(FINGERPRINT_PATH.read_text())
    except Exception:
        return {
            "bridge_version": "0.4.0",
            "fingerprint_status": "unavailable",
        }


def compact_game_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": result.get("status"),
        "winner": result.get("winner"),
        "named_winner": result.get("named_winner"),
        "win_reason": result.get("win_reason"),
        "turn_count": result.get("turn_count"),
        "decisions": result.get("decisions"),
        "counts": result.get("counts", {}),
        "opponent_counts": result.get("opponent_counts", {}),
        "trace_tail": result.get("trace", [])[-24:],
        "errors": result.get("errors", [])[-8:],
    }


def run_autoplay_game_impl(
    main_a: list[int],
    extra_a: list[int],
    main_b: list[int],
    extra_b: list[int],
    *,
    a_seat: int,
    seed: int,
    profile_a: str,
    profile_b: str,
    reaction_priority_a: list[int],
    reaction_priority_b: list[int],
    target_priority_a: list[int],
    target_priority_b: list[int],
    reaction_hold_windows_a: dict[int, int],
    reaction_hold_windows_b: dict[int, int],
    reaction_min_summons_a: dict[int, int],
    reaction_min_summons_b: dict[int, int],
    opening_hand_a: list[int] | None = None,
    opening_hand_b: list[int] | None = None,
    max_decisions: int = 600,
    max_process_steps: int = 6000,
    stop_after_turns: int = 0,
) -> dict[str, Any]:
    a_seat = 0 if int(a_seat) == 0 else 1
    if a_seat == 0:
        seat_main = (main_a, main_b)
        seat_extra = (extra_a, extra_b)
        seat_opening = (opening_hand_a, opening_hand_b)
        profiles = (profile_a, profile_b)
        reactions = (reaction_priority_a, reaction_priority_b)
        targets = (target_priority_a, target_priority_b)
        holds = (reaction_hold_windows_a, reaction_hold_windows_b)
        min_summons = (reaction_min_summons_a, reaction_min_summons_b)
    else:
        seat_main = (main_b, main_a)
        seat_extra = (extra_b, extra_a)
        seat_opening = (opening_hand_b, opening_hand_a)
        profiles = (profile_b, profile_a)
        reactions = (reaction_priority_b, reaction_priority_a)
        targets = (target_priority_b, target_priority_a)
        holds = (reaction_hold_windows_b, reaction_hold_windows_a)
        min_summons = (reaction_min_summons_b, reaction_min_summons_a)

    duel = DuelBridge(
        get_core(),
        get_db(),
        seat_main[0],
        seat_extra[0],
        seat_opening[0] or None,
        opponent_main=seat_main[1],
        opponent_extra=seat_extra[1],
        opponent_opening_hand=seat_opening[1] or None,
        seed=int(seed),
    )
    try:
        result = duel.autoplay(
            profiles=profiles,
            reaction_priorities=reactions,
            target_priorities=targets,
            reaction_hold_windows=holds,
            reaction_min_opponent_summons=min_summons,
            max_decisions=max(20, min(int(max_decisions), 1500)),
            max_process_steps=max(200, min(int(max_process_steps), 12000)),
            stop_after_turns=max(0, int(stop_after_turns)),
        )
    finally:
        duel.close()

    result["a_seat"] = a_seat
    if result.get("winner") in (0, 1):
        result["named_winner"] = (
            "A"
            if int(result["winner"]) == a_seat
            else "B"
        )
    else:
        result["named_winner"] = None
    result["runtime_fingerprint"] = runtime_fingerprint()
    return result


def run_bo3_impl(
    main_a: list[int],
    extra_a: list[int],
    main_b: list[int],
    extra_b: list[int],
    *,
    seed: int,
    profile_a: str,
    profile_b: str,
    reaction_priority_a: list[int],
    reaction_priority_b: list[int],
    target_priority_a: list[int],
    target_priority_b: list[int],
    reaction_hold_windows_a: dict[int, int],
    reaction_hold_windows_b: dict[int, int],
    reaction_min_summons_a: dict[int, int],
    reaction_min_summons_b: dict[int, int],
    max_decisions: int,
    max_process_steps: int,
) -> dict[str, Any]:
    score = {"A": 0, "B": 0}
    games: list[dict[str, Any]] = []
    a_seat = 0

    for game_index in range(3):
        result = run_autoplay_game_impl(
            main_a,
            extra_a,
            main_b,
            extra_b,
            a_seat=a_seat,
            seed=int(seed) + game_index,
            profile_a=profile_a,
            profile_b=profile_b,
            reaction_priority_a=reaction_priority_a,
            reaction_priority_b=reaction_priority_b,
            target_priority_a=target_priority_a,
            target_priority_b=target_priority_b,
            reaction_hold_windows_a=reaction_hold_windows_a,
            reaction_hold_windows_b=reaction_hold_windows_b,
            reaction_min_summons_a=reaction_min_summons_a,
            reaction_min_summons_b=reaction_min_summons_b,
            max_decisions=max_decisions,
            max_process_steps=max_process_steps,
        )
        compact = compact_game_result(result)
        compact["game"] = game_index + 1
        compact["a_seat"] = a_seat
        games.append(compact)

        winner = result.get("named_winner")
        if winner not in {"A", "B"}:
            return {
                "status": "incomplete",
                "match_winner": None,
                "score": score,
                "games": games,
                "reason": f"game_{game_index + 1}_{result.get('status')}",
            }

        score[winner] += 1
        if score[winner] >= 2:
            return {
                "status": "complete",
                "match_winner": winner,
                "score": score,
                "games": games,
            }

        loser = "B" if winner == "A" else "A"
        a_seat = 0 if loser == "A" else 1

    return {
        "status": "complete",
        "match_winner": "A" if score["A"] > score["B"] else "B",
        "score": score,
        "games": games,
    }


def build_handtrap_opponent(
    handtrap_codes: list[int] | None,
) -> tuple[list[int], list[int]]:
    requested = clean_codes(handtrap_codes)
    opening = requested[:5]
    while len(opening) < 5:
        opening.append(DUMMY_OPPONENT)
    main = list(opening)
    while len(main) < 40:
        main.append(DUMMY_OPPONENT)
    return main, opening


def route_goal_reached(
    result: dict[str, Any],
    *,
    min_monsters: int = 0,
    min_backrow: int = 0,
    min_hand: int = 0,
) -> bool:
    counts = result.get("counts", {})
    return (
        int(counts.get("monster_zone", 0)) >= int(min_monsters)
        and int(counts.get("spell_trap_zone", 0)) >= int(min_backrow)
        and int(counts.get("hand", 0)) >= int(min_hand)
    )


def route_score(
    result: dict[str, Any],
    *,
    min_monsters: int = 0,
    min_backrow: int = 0,
    min_hand: int = 0,
) -> float:
    counts = result.get("counts", {})
    opponent = result.get("opponent_counts", {})
    score = (
        12.0 * int(counts.get("monster_zone", 0))
        + 7.0 * int(counts.get("spell_trap_zone", 0))
        + 1.25 * int(counts.get("hand", 0))
        + 0.25 * int(counts.get("graveyard", 0))
        - 2.0 * int(opponent.get("monster_zone", 0))
        - 1.0 * int(opponent.get("spell_trap_zone", 0))
    )
    if route_goal_reached(
        result,
        min_monsters=min_monsters,
        min_backrow=min_backrow,
        min_hand=min_hand,
    ):
        score += 1000.0
    if result.get("status") in {"retry_error", "invalid_choice", "unsupported_prompt"}:
        score -= 500.0
    score -= 0.05 * len(result.get("trace", []))
    return round(score, 3)


def run_policy_once(
    main: list[int],
    extra: list[int],
    opening_hand: list[int] | None,
    player_choices: list[int] | None,
    handtrap_codes: list[int] | None,
    opponent_target_priority: list[int] | None,
    *,
    seed: int,
    auto_player: bool,
    max_player_decisions: int,
    max_process_steps: int,
) -> dict[str, Any]:
    opponent_main, opponent_opening = build_handtrap_opponent(handtrap_codes)
    duel = DuelBridge(
        get_core(),
        get_db(),
        main,
        extra,
        opening_hand or None,
        opponent_main=opponent_main,
        opponent_extra=[],
        opponent_opening_hand=opponent_opening,
        seed=int(seed),
    )
    try:
        result = duel.replay_policy(
            player_choices,
            opponent_handtrap_codes=handtrap_codes,
            opponent_target_priority=opponent_target_priority,
            auto_player=auto_player,
            max_player_decisions=max_player_decisions,
            max_process_steps=max_process_steps,
        )
        result["opponent_opening_hand"] = [
            {"code": code, "name": get_db().name(code)}
            for code in opponent_opening
        ]
        return result
    finally:
        duel.close()


def search_combo_routes_impl(
    main: list[int],
    extra: list[int],
    opening_hand: list[int] | None,
    handtrap_codes: list[int] | None,
    opponent_target_priority: list[int] | None,
    *,
    seed: int,
    max_depth: int,
    beam_width: int,
    branch_limit: int,
    max_nodes: int,
    min_monsters: int,
    min_backrow: int,
    min_hand: int,
) -> dict[str, Any]:
    frontier: list[list[int]] = [[]]
    evaluated: list[dict[str, Any]] = []
    visited: set[tuple[int, ...]] = set()
    nodes = 0

    max_depth = max(1, min(int(max_depth), 12))
    beam_width = max(1, min(int(beam_width), 12))
    branch_limit = max(1, min(int(branch_limit), 12))
    max_nodes = max(4, min(int(max_nodes), 240))

    for depth in range(max_depth + 1):
        layer: list[dict[str, Any]] = []
        for path in frontier:
            key = tuple(path)
            if key in visited:
                continue
            visited.add(key)
            result = run_policy_once(
                main,
                extra,
                opening_hand,
                path,
                handtrap_codes,
                opponent_target_priority,
                seed=seed,
                auto_player=False,
                max_player_decisions=max_depth + 8,
                max_process_steps=1600,
            )
            nodes += 1
            row = {
                "choices": path,
                "depth": len(path),
                "score": route_score(
                    result,
                    min_monsters=min_monsters,
                    min_backrow=min_backrow,
                    min_hand=min_hand,
                ),
                "goal_reached": route_goal_reached(
                    result,
                    min_monsters=min_monsters,
                    min_backrow=min_backrow,
                    min_hand=min_hand,
                ),
                "result": result,
            }
            evaluated.append(row)
            layer.append(row)
            if nodes >= max_nodes:
                break

        if nodes >= max_nodes or depth >= max_depth:
            break

        layer.sort(key=lambda row: (bool(row["goal_reached"]), float(row["score"])), reverse=True)
        parents = layer[:beam_width]
        next_frontier: list[list[int]] = []
        for row in parents:
            result = row["result"]
            if result.get("status") != "awaiting_choice":
                continue
            options = result.get("decision", {}).get("options", [])
            if not options:
                continue
            non_terminal = [
                (index, option)
                for index, option in enumerate(options)
                if option.get("kind") not in {"end", "battle"}
            ]
            selected_options = non_terminal or list(enumerate(options))
            for index, _option in selected_options[:branch_limit]:
                candidate = [*row["choices"], int(index)]
                if tuple(candidate) not in visited:
                    next_frontier.append(candidate)

        if not next_frontier:
            break
        frontier = next_frontier[: max(beam_width * branch_limit, beam_width)]

    evaluated.sort(
        key=lambda row: (bool(row["goal_reached"]), float(row["score"]), row["depth"]),
        reverse=True,
    )
    top = []
    for row in evaluated[:5]:
        result = row["result"]
        top.append(
            {
                "choices": row["choices"],
                "depth": row["depth"],
                "score": row["score"],
                "goal_reached": row["goal_reached"],
                "status": result.get("status"),
                "trace": result.get("trace", []),
                "handtraps_used": result.get("handtraps_used", []),
                "counts": result.get("counts", {}),
                "opponent_counts": result.get("opponent_counts", {}),
                "next_decision": result.get("decision"),
                "errors": result.get("errors", []),
            }
        )
    return {
        "nodes_evaluated": nodes,
        "max_nodes": max_nodes,
        "max_depth": max_depth,
        "beam_width": beam_width,
        "branch_limit": branch_limit,
        "goal": {
            "min_monsters": int(min_monsters),
            "min_backrow": int(min_backrow),
            "min_hand": int(min_hand),
        },
        "top_routes": top,
    }


mcp = MCPServer("verify-tournament-deck-edopro-sim")


@mcp.tool()
def edopro_engine_status() -> dict[str, Any]:
    """Report the installed ocgcore/CardScripts/BabelCDB runtime and v0.4 capability matrix."""
    core = get_core()
    major, minor = core.version()
    return {
        "ok": True,
        "bridge_version": "0.4.0",
        "ocgcore_version": f"{major}.{minor}",
        "paths": {
            "library": str(LIB_PATH),
            "cardscripts": str(SCRIPTS),
            "cards_cdb": str(CDB_PATH),
        },
        "rules_profile": "OCG Master Rule 5",
        "runtime_fingerprint": runtime_fingerprint(),
        "capabilities": {
            "real_ocgcore_rules_engine": True,
            "ydk_export": True,
            "deck_structure_validation": True,
            "card_lookup": True,
            "opening_hand_sampling": True,
            "deterministic_choice_replay": True,
            "fixed_opening_hand_replay": True,
            "heuristic_combo_route_search": True,
            "autonomous_handtrap_adversary": True,
            "batch_handtrap_stress": True,
            "strategic_reaction_timing": True,
            "autonomous_dual_policy_game": True,
            "seat_swapped_bo3": True,
            "full_match_batch": True,
            "autonomous_full_match_bot": "heuristic",
        },
    }


@mcp.tool()
def edopro_export_ydk(
    main: list[int],
    extra: list[int] | None = None,
    side: list[int] | None = None,
) -> str:
    """Export card passcodes as standard EDOPro .ydk deck text."""
    main_codes = clean_codes(main)
    extra_codes = clean_codes(extra)
    side_codes = clean_codes(side)
    lines = ["#created by Verify Tournament Deck v0.4.0", "#main"]
    lines.extend(str(code) for code in main_codes)
    lines.append("#extra")
    lines.extend(str(code) for code in extra_codes)
    lines.append("!side")
    lines.extend(str(code) for code in side_codes)
    return "\n".join(lines) + "\n"


@mcp.tool()
def edopro_validate_deck(
    main: list[int],
    extra: list[int] | None = None,
    side: list[int] | None = None,
) -> dict[str, Any]:
    """Validate deck structure and confirm passcodes exist in the installed EDOPro card database."""
    return validate_input_deck(clean_codes(main), clean_codes(extra), side)


@mcp.tool()
def edopro_search_cards(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search the installed BabelCDB card database by card name."""
    return get_db().search(str(query), limit)


@mcp.tool()
def edopro_sample_opening_hands(
    main: list[int],
    trials: int = 1000,
    hand_size: int = 5,
    seed: int = 1,
) -> dict[str, Any]:
    """Sample opening hands. This is Monte Carlo deck sampling, not an ocgcore game."""
    deck = clean_codes(main)
    trials = max(1, min(int(trials), 100000))
    hand_size = max(1, min(int(hand_size), 10))
    if len(deck) < hand_size:
        raise ValueError("Main Deck is smaller than requested hand size.")
    rng = random.Random(int(seed))
    db = get_db()
    sample_limit = min(12, trials)
    samples: list[list[dict[str, Any]]] = []
    for index in range(trials):
        hand = rng.sample(deck, hand_size)
        if index < sample_limit:
            samples.append([{"code": code, "name": db.name(code)} for code in hand])
    return {
        "trials": trials,
        "hand_size": hand_size,
        "seed": int(seed),
        "sample_hands": samples,
        "note": "Use Verify Tournament Deck starter definitions to classify these hands into starter/brick categories.",
    }


@mcp.tool()
def edopro_replay_choices(
    main: list[int],
    extra: list[int] | None = None,
    opening_hand: list[int] | None = None,
    choices: list[int] | None = None,
    seed: int = 1,
    max_process_steps: int = 500,
) -> dict[str, Any]:
    """Replay a deterministic action path through real ocgcore and stop at the next branch.

    choices contains zero-based option indices. Call with [] to inspect the first
    decision, append the selected index, then call again. This validates a known
    DSL/combo route without pretending the bridge is an autonomous duel AI.
    """
    main_codes = clean_codes(main)
    extra_codes = clean_codes(extra)
    hand_codes = clean_codes(opening_hand)
    path = clean_codes(choices)
    validation = validate_input_deck(main_codes, extra_codes)
    if not validation["ok_for_simulation"]:
        return {"status": "invalid_deck", "validation": validation}
    if hand_codes and len(hand_codes) != 5:
        return {
            "status": "invalid_opening_hand",
            "reason": "opening_hand must contain exactly 5 card passcodes when supplied",
        }

    duel = DuelBridge(
        get_core(),
        get_db(),
        main_codes,
        extra_codes,
        hand_codes or None,
        seed=int(seed),
    )
    try:
        result = duel.replay(
            path,
            max_process_steps=max(20, min(int(max_process_steps), 5000)),
        )
        result["validation"] = validation
        result["rules_profile"] = "OCG Master Rule 5"
        result["opening_hand_requested"] = hand_codes or None
        return result
    finally:
        duel.close()


@mcp.tool()
def edopro_handtrap_stress(
    main: list[int],
    extra: list[int] | None = None,
    opening_hand: list[int] | None = None,
    handtrap_codes: list[int] | None = None,
    player_choices: list[int] | None = None,
    opponent_target_priority: list[int] | None = None,
    auto_player: bool = False,
    seed: int = 1,
    max_player_decisions: int = 80,
    max_process_steps: int = 1200,
) -> dict[str, Any]:
    """Run a real-ocgcore line while the opponent automatically fires supplied hand traps at the first legal timing.

    Supply handtrap_codes as card passcodes. The bridge fixes up to five supplied
    cards into the opponent opening hand and fills the rest with inert test cards.
    This is a deterministic stress scenario, not a tournament-legal opponent deck.
    """
    main_codes = clean_codes(main)
    extra_codes = clean_codes(extra)
    hand_codes = clean_codes(opening_hand)
    traps = clean_codes(handtrap_codes)
    validation = validate_input_deck(main_codes, extra_codes)
    if not validation["ok_for_simulation"]:
        return {"status": "invalid_deck", "validation": validation}
    if hand_codes and len(hand_codes) != 5:
        return {
            "status": "invalid_opening_hand",
            "reason": "opening_hand must contain exactly 5 card passcodes when supplied",
        }
    missing_traps = [code for code in traps if not get_db().exists(code)]
    if missing_traps:
        return {
            "status": "invalid_handtrap_codes",
            "missing_codes": sorted(set(missing_traps)),
        }
    result = run_policy_once(
        main_codes,
        extra_codes,
        hand_codes or None,
        clean_codes(player_choices),
        traps,
        clean_codes(opponent_target_priority),
        seed=int(seed),
        auto_player=bool(auto_player),
        max_player_decisions=max(1, min(int(max_player_decisions), 200)),
        max_process_steps=max(50, min(int(max_process_steps), 5000)),
    )
    result["validation"] = validation
    result["rules_profile"] = "OCG Master Rule 5"
    result["handtrap_policy"] = "first legal activation by supplied priority"
    return result


@mcp.tool()
def edopro_search_combo_routes(
    main: list[int],
    extra: list[int] | None = None,
    opening_hand: list[int] | None = None,
    handtrap_codes: list[int] | None = None,
    opponent_target_priority: list[int] | None = None,
    seed: int = 1,
    max_depth: int = 6,
    beam_width: int = 4,
    branch_limit: int = 6,
    max_nodes: int = 120,
    min_monsters: int = 0,
    min_backrow: int = 0,
    min_hand: int = 0,
) -> dict[str, Any]:
    """Bounded beam-search over candidate choices with automatic opponent hand traps.

    This searches real ocgcore decision branches and ranks routes with a transparent
    board-presence heuristic. It is useful for finding candidate penetration routes,
    but it is not a proof of globally optimal Yu-Gi-Oh! play.
    """
    main_codes = clean_codes(main)
    extra_codes = clean_codes(extra)
    hand_codes = clean_codes(opening_hand)
    traps = clean_codes(handtrap_codes)
    validation = validate_input_deck(main_codes, extra_codes)
    if not validation["ok_for_simulation"]:
        return {"status": "invalid_deck", "validation": validation}
    if hand_codes and len(hand_codes) != 5:
        return {
            "status": "invalid_opening_hand",
            "reason": "opening_hand must contain exactly 5 card passcodes when supplied",
        }
    missing_traps = [code for code in traps if not get_db().exists(code)]
    if missing_traps:
        return {
            "status": "invalid_handtrap_codes",
            "missing_codes": sorted(set(missing_traps)),
        }

    result = search_combo_routes_impl(
        main_codes,
        extra_codes,
        hand_codes or None,
        traps,
        clean_codes(opponent_target_priority),
        seed=int(seed),
        max_depth=max_depth,
        beam_width=beam_width,
        branch_limit=branch_limit,
        max_nodes=max_nodes,
        min_monsters=max(0, int(min_monsters)),
        min_backrow=max(0, int(min_backrow)),
        min_hand=max(0, int(min_hand)),
    )
    result["validation"] = validation
    result["rules_profile"] = "OCG Master Rule 5"
    result["handtrap_policy"] = "first legal activation by supplied priority"
    result["optimality"] = "bounded heuristic search; not global-optimality proof"
    return result


@mcp.tool()
def edopro_batch_stress(
    main: list[int],
    extra: list[int] | None = None,
    handtrap_codes: list[int] | None = None,
    opponent_target_priority: list[int] | None = None,
    trials: int = 20,
    seed: int = 1,
    min_monsters: int = 1,
    min_backrow: int = 0,
    min_hand: int = 0,
    max_player_decisions: int = 60,
    max_process_steps: int = 1200,
) -> dict[str, Any]:
    """Run multiple automatic ocgcore stress games with sampled five-card openings.

    Candidate play uses the v0.4 greedy legal-action policy; the opponent uses
    supplied hand traps at their first legal timing. The reported pass rate is a
    stress-test success rate against the requested board thresholds, not a match win rate.
    """
    main_codes = clean_codes(main)
    extra_codes = clean_codes(extra)
    traps = clean_codes(handtrap_codes)
    validation = validate_input_deck(main_codes, extra_codes)
    if not validation["ok_for_simulation"]:
        return {"status": "invalid_deck", "validation": validation}
    if len(main_codes) < 5:
        return {"status": "invalid_deck", "reason": "main deck needs at least 5 cards"}
    missing_traps = [code for code in traps if not get_db().exists(code)]
    if missing_traps:
        return {
            "status": "invalid_handtrap_codes",
            "missing_codes": sorted(set(missing_traps)),
        }

    trials = max(1, min(int(trials), 50))
    rng = random.Random(int(seed))
    statuses: Counter[str] = Counter()
    passes = 0
    handtrap_usage: Counter[int] = Counter()
    samples: list[dict[str, Any]] = []

    for index in range(trials):
        opening = rng.sample(main_codes, 5)
        result = run_policy_once(
            main_codes,
            extra_codes,
            opening,
            None,
            traps,
            clean_codes(opponent_target_priority),
            seed=int(seed) + index,
            auto_player=True,
            max_player_decisions=max(1, min(int(max_player_decisions), 160)),
            max_process_steps=max(50, min(int(max_process_steps), 5000)),
        )
        status = str(result.get("status", "unknown"))
        statuses[status] += 1
        passed = route_goal_reached(
            result,
            min_monsters=max(0, int(min_monsters)),
            min_backrow=max(0, int(min_backrow)),
            min_hand=max(0, int(min_hand)),
        )
        passes += int(passed)
        for row in result.get("handtraps_used", []):
            handtrap_usage[int(row.get("code", 0))] += 1
        if index < 10:
            samples.append(
                {
                    "trial": index,
                    "opening_hand": [
                        {"code": code, "name": get_db().name(code)}
                        for code in opening
                    ],
                    "passed": passed,
                    "status": status,
                    "counts": result.get("counts", {}),
                    "handtraps_used": result.get("handtraps_used", []),
                    "trace_tail": result.get("trace", [])[-12:],
                    "errors": result.get("errors", [])[-5:],
                }
            )

    return {
        "trials": trials,
        "seed": int(seed),
        "passes": passes,
        "pass_rate": round(passes / trials, 6),
        "goal": {
            "min_monsters": max(0, int(min_monsters)),
            "min_backrow": max(0, int(min_backrow)),
            "min_hand": max(0, int(min_hand)),
        },
        "statuses": dict(statuses),
        "handtrap_usage": [
            {
                "code": code,
                "name": get_db().name(code),
                "activations": count,
            }
            for code, count in handtrap_usage.most_common()
            if code
        ],
        "samples": samples,
        "validation": validation,
        "rules_profile": "OCG Master Rule 5",
        "candidate_policy": "greedy legal-action heuristic",
        "handtrap_policy": "first legal activation by supplied priority",
        "warning": "This is an automated stress-test pass rate, not a tournament match win rate.",
    }


@mcp.tool()
def edopro_evaluate_handtrap_timing(
    main: list[int],
    extra: list[int] | None = None,
    opening_hand: list[int] | None = None,
    handtrap_code: int = 0,
    max_hold_windows: int = 3,
    min_opponent_summons: int = 0,
    seed: int = 1,
    profile: str = "balanced",
) -> dict[str, Any]:
    """Compare several legal activation windows for one supplied hand trap.

    The opponent is an inert 40-card shell with the requested hand trap fixed
    in its opening hand. Candidate play is heuristic. Lower candidate board
    score means the hand-trap timing disrupted the candidate more strongly.
    """
    main_codes = clean_codes(main)
    extra_codes = clean_codes(extra)
    hand_codes = clean_codes(opening_hand)
    code = int(handtrap_code)
    validation = validate_input_deck(main_codes, extra_codes)
    if not validation["ok_for_simulation"]:
        return {"status": "invalid_deck", "validation": validation}
    if hand_codes and len(hand_codes) != 5:
        return {
            "status": "invalid_opening_hand",
            "reason": "opening_hand must contain exactly 5 card passcodes when supplied",
        }
    if not code or not get_db().exists(code):
        return {"status": "invalid_handtrap_code", "code": code}

    opponent_main, opponent_opening = build_handtrap_opponent([code])
    rows: list[dict[str, Any]] = []
    max_hold_windows = max(0, min(int(max_hold_windows), 8))
    for hold in range(max_hold_windows + 1):
        result = run_autoplay_game_impl(
            main_codes,
            extra_codes,
            opponent_main,
            [],
            a_seat=0,
            seed=int(seed),
            profile_a=profile,
            profile_b="passive",
            reaction_priority_a=[],
            reaction_priority_b=[code],
            target_priority_a=[],
            target_priority_b=[],
            reaction_hold_windows_a={},
            reaction_hold_windows_b={code: hold},
            reaction_min_summons_a={},
            reaction_min_summons_b={code: max(0, int(min_opponent_summons))},
            opening_hand_a=hand_codes or None,
            opening_hand_b=opponent_opening,
            max_decisions=220,
            max_process_steps=3500,
            stop_after_turns=1,
        )
        score = route_score(result)
        activations = [
            row
            for row in result.get("trace", [])
            if row.get("player") == 1
            and row.get("kind") == "chain"
            and int(row.get("code", 0)) == code
        ]
        rows.append(
            {
                "hold_legal_windows": hold,
                "status": result.get("status"),
                "activated": bool(activations),
                "activation": activations[0] if activations else None,
                "candidate_board_score": score,
                "candidate_counts": result.get("counts", {}),
                "trace_tail": result.get("trace", [])[-18:],
                "errors": result.get("errors", [])[-6:],
            }
        )

    activated_rows = [row for row in rows if row["activated"]]
    best = min(activated_rows, key=lambda row: row["candidate_board_score"]) if activated_rows else None
    return {
        "status": "complete" if rows else "incomplete",
        "handtrap": {"code": code, "name": get_db().name(code)},
        "min_opponent_summons": max(0, int(min_opponent_summons)),
        "timings": rows,
        "strongest_observed_timing": best,
        "interpretation": (
            "Lower candidate_board_score means stronger disruption in this bounded "
            "heuristic first-turn scenario; it is not a proof of globally optimal timing."
        ),
        "runtime_fingerprint": runtime_fingerprint(),
    }


@mcp.tool()
def edopro_autoplay_game(
    main_a: list[int],
    extra_a: list[int] | None,
    main_b: list[int],
    extra_b: list[int] | None,
    seed: int = 1,
    a_seat: int = 0,
    profile_a: str = "balanced",
    profile_b: str = "balanced",
    reaction_priority_a: list[int] | None = None,
    reaction_priority_b: list[int] | None = None,
    target_priority_a: list[int] | None = None,
    target_priority_b: list[int] | None = None,
    reaction_hold_windows_a: dict[str, int] | None = None,
    reaction_hold_windows_b: dict[str, int] | None = None,
    reaction_min_summons_a: dict[str, int] | None = None,
    reaction_min_summons_b: dict[str, int] | None = None,
    max_decisions: int = 600,
    max_process_steps: int = 6000,
) -> dict[str, Any]:
    """Run one headless real-ocgcore duel with heuristic policies for both decks."""
    a_main = clean_codes(main_a)
    a_extra = clean_codes(extra_a)
    b_main = clean_codes(main_b)
    b_extra = clean_codes(extra_b)
    validation_a = validate_input_deck(a_main, a_extra)
    validation_b = validate_input_deck(b_main, b_extra)
    if not validation_a["ok_for_simulation"] or not validation_b["ok_for_simulation"]:
        return {
            "status": "invalid_deck",
            "validation_a": validation_a,
            "validation_b": validation_b,
        }
    result = run_autoplay_game_impl(
        a_main,
        a_extra,
        b_main,
        b_extra,
        a_seat=a_seat,
        seed=seed,
        profile_a=profile_a,
        profile_b=profile_b,
        reaction_priority_a=clean_codes(reaction_priority_a),
        reaction_priority_b=clean_codes(reaction_priority_b),
        target_priority_a=clean_codes(target_priority_a),
        target_priority_b=clean_codes(target_priority_b),
        reaction_hold_windows_a=normalize_int_map(reaction_hold_windows_a),
        reaction_hold_windows_b=normalize_int_map(reaction_hold_windows_b),
        reaction_min_summons_a=normalize_int_map(reaction_min_summons_a),
        reaction_min_summons_b=normalize_int_map(reaction_min_summons_b),
        max_decisions=max_decisions,
        max_process_steps=max_process_steps,
    )
    result["validation_a"] = validation_a
    result["validation_b"] = validation_b
    result["policy_note"] = (
        "Both players use transparent heuristic action selection. This is an "
        "autonomous rules-valid duel harness, not an optimal-play engine."
    )
    return result


@mcp.tool()
def edopro_bo3_match(
    main_a: list[int],
    extra_a: list[int] | None,
    main_b: list[int],
    extra_b: list[int] | None,
    seed: int = 1,
    profile_a: str = "balanced",
    profile_b: str = "balanced",
    reaction_priority_a: list[int] | None = None,
    reaction_priority_b: list[int] | None = None,
    target_priority_a: list[int] | None = None,
    target_priority_b: list[int] | None = None,
    reaction_hold_windows_a: dict[str, int] | None = None,
    reaction_hold_windows_b: dict[str, int] | None = None,
    reaction_min_summons_a: dict[str, int] | None = None,
    reaction_min_summons_b: dict[str, int] | None = None,
    max_decisions: int = 600,
    max_process_steps: int = 6000,
) -> dict[str, Any]:
    """Run a no-side best-of-three match. The previous-game loser is put in seat 0 next game."""
    a_main = clean_codes(main_a)
    a_extra = clean_codes(extra_a)
    b_main = clean_codes(main_b)
    b_extra = clean_codes(extra_b)
    validation_a = validate_input_deck(a_main, a_extra)
    validation_b = validate_input_deck(b_main, b_extra)
    if not validation_a["ok_for_simulation"] or not validation_b["ok_for_simulation"]:
        return {
            "status": "invalid_deck",
            "validation_a": validation_a,
            "validation_b": validation_b,
        }
    result = run_bo3_impl(
        a_main,
        a_extra,
        b_main,
        b_extra,
        seed=seed,
        profile_a=profile_a,
        profile_b=profile_b,
        reaction_priority_a=clean_codes(reaction_priority_a),
        reaction_priority_b=clean_codes(reaction_priority_b),
        target_priority_a=clean_codes(target_priority_a),
        target_priority_b=clean_codes(target_priority_b),
        reaction_hold_windows_a=normalize_int_map(reaction_hold_windows_a),
        reaction_hold_windows_b=normalize_int_map(reaction_hold_windows_b),
        reaction_min_summons_a=normalize_int_map(reaction_min_summons_a),
        reaction_min_summons_b=normalize_int_map(reaction_min_summons_b),
        max_decisions=max_decisions,
        max_process_steps=max_process_steps,
    )
    result["validation_a"] = validation_a
    result["validation_b"] = validation_b
    result["side_deck"] = False
    result["seat_policy"] = (
        "Game 1: A in seat 0. Later games: previous-game loser is placed in seat 0, "
        "modeling the loser choosing to go first."
    )
    result["runtime_fingerprint"] = runtime_fingerprint()
    return result


@mcp.tool()
def edopro_full_match_batch(
    main_a: list[int],
    extra_a: list[int] | None,
    main_b: list[int],
    extra_b: list[int] | None,
    matches: int = 5,
    seed: int = 1,
    profile_a: str = "balanced",
    profile_b: str = "balanced",
    reaction_priority_a: list[int] | None = None,
    reaction_priority_b: list[int] | None = None,
    target_priority_a: list[int] | None = None,
    target_priority_b: list[int] | None = None,
    reaction_hold_windows_a: dict[str, int] | None = None,
    reaction_hold_windows_b: dict[str, int] | None = None,
    reaction_min_summons_a: dict[str, int] | None = None,
    reaction_min_summons_b: dict[str, int] | None = None,
    max_decisions: int = 600,
    max_process_steps: int = 6000,
) -> dict[str, Any]:
    """Run repeated no-side BO3 matches and aggregate heuristic-agent results."""
    a_main = clean_codes(main_a)
    a_extra = clean_codes(extra_a)
    b_main = clean_codes(main_b)
    b_extra = clean_codes(extra_b)
    validation_a = validate_input_deck(a_main, a_extra)
    validation_b = validate_input_deck(b_main, b_extra)
    if not validation_a["ok_for_simulation"] or not validation_b["ok_for_simulation"]:
        return {
            "status": "invalid_deck",
            "validation_a": validation_a,
            "validation_b": validation_b,
        }

    matches = max(1, min(int(matches), 20))
    completed = 0
    wins = Counter()
    rows: list[dict[str, Any]] = []
    for index in range(matches):
        match = run_bo3_impl(
            a_main,
            a_extra,
            b_main,
            b_extra,
            seed=int(seed) + index * 100,
            profile_a=profile_a,
            profile_b=profile_b,
            reaction_priority_a=clean_codes(reaction_priority_a),
            reaction_priority_b=clean_codes(reaction_priority_b),
            target_priority_a=clean_codes(target_priority_a),
            target_priority_b=clean_codes(target_priority_b),
            reaction_hold_windows_a=normalize_int_map(reaction_hold_windows_a),
            reaction_hold_windows_b=normalize_int_map(reaction_hold_windows_b),
            reaction_min_summons_a=normalize_int_map(reaction_min_summons_a),
            reaction_min_summons_b=normalize_int_map(reaction_min_summons_b),
            max_decisions=max_decisions,
            max_process_steps=max_process_steps,
        )
        if match.get("status") == "complete":
            completed += 1
            if match.get("match_winner") in {"A", "B"}:
                wins[str(match["match_winner"])] += 1
        rows.append(
            {
                "match": index + 1,
                "status": match.get("status"),
                "winner": match.get("match_winner"),
                "score": match.get("score"),
                "games": match.get("games", []),
                "reason": match.get("reason"),
            }
        )

    return {
        "status": "complete" if completed == matches else "partially_complete",
        "matches_requested": matches,
        "matches_completed": completed,
        "completion_rate": round(completed / matches, 6),
        "match_wins": {"A": wins["A"], "B": wins["B"]},
        "heuristic_match_win_rate_a": (
            round(wins["A"] / completed, 6) if completed else None
        ),
        "matches": rows,
        "validation_a": validation_a,
        "validation_b": validation_b,
        "side_deck": False,
        "runtime_fingerprint": runtime_fingerprint(),
        "warning": (
            "The win rate is produced by deterministic heuristic agents on real "
            "ocgcore rules. It is not a tournament win-rate estimate and must be "
            "calibrated against human/EDOPro match data before Reality Calibration."
        ),
    }


_selftest_cache: dict[str, Any] | None = None


def run_engine_selftest() -> dict[str, Any]:
    """Create and process a real ocgcore duel once to prove the runtime is executable."""
    global _selftest_cache
    if _selftest_cache is not None:
        return _selftest_cache

    duel: DuelBridge | None = None
    try:
        db = get_db()
        if not db.exists(DUMMY_OPPONENT):
            raise RuntimeError(f"self-test card {DUMMY_OPPONENT} is missing from cards.cdb")
        duel = DuelBridge(
            get_core(),
            db,
            [DUMMY_OPPONENT] * 40,
            [],
            opening_hand=None,
            seed=1,
        )
        result = duel.replay([], max_process_steps=120)
        ok = result.get("status") == "awaiting_choice"
        _selftest_cache = {
            "ok": ok,
            "status": result.get("status"),
            "decision": result.get("decision"),
            "counts": result.get("counts"),
            "errors": result.get("errors", [])[-5:],
        }
        return _selftest_cache
    except Exception as exc:
        _selftest_cache = {"ok": False, "status": "exception", "error": str(exc)}
        return _selftest_cache
    finally:
        if duel is not None:
            duel.close()


async def health(_request):
    try:
        major, minor = get_core().version()
        selftest = run_engine_selftest()
        ok = bool(selftest.get("ok"))
        return JSONResponse(
            {
                "ok": ok,
                "service": "verify-tournament-deck-edopro-sim",
                "version": "0.4.0",
                "ocgcore": f"{major}.{minor}",
                "cards_cdb": CDB_PATH.exists(),
                "cardscripts": SCRIPTS.exists(),
                "engine_selftest": selftest,
            },
            status_code=200 if ok else 503,
        )
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=503)


mcp_app = mcp.streamable_http_app(
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    host="0.0.0.0",
)

@contextlib.asynccontextmanager
async def lifespan(_app: Starlette):
    async with mcp.session_manager.run():
        yield

app = Starlette(
    routes=[
        Route("/healthz", health, methods=["GET"]),
        Mount("/", app=mcp_app),
    ],
    lifespan=lifespan,
)
