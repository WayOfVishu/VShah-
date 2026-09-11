-- SQLite schema for League-ML.
-- Matches the data model in docs/project-charter.md Section 12.
-- This file is pure DDL (no learning ceiling beyond SQL you already know well),
-- so it's written out in full. Loaded by leagueml/storage/db.py::init_db().
--
-- v3 changes from the draft, each marked (v3) below: matches.game_version,
-- participants.riot_participant_num, and the participant_frames table.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS matches (
    match_id        TEXT PRIMARY KEY,
    patch           TEXT NOT NULL,      -- major.minor of game_version, e.g. "16.18" -- compare against config.TARGET_PATCH
    game_version    TEXT NOT NULL,      -- (v3) raw info.gameVersion, e.g. "16.18.712.4321" -- kept so a wrong patch parse can be redone
    game_start_ts   INTEGER NOT NULL,   -- epoch millis, from match.info.gameStartTimestamp
    duration_s      INTEGER NOT NULL,   -- match.info.gameDuration (seconds)
    queue_id        INTEGER NOT NULL,   -- e.g. 420 = ranked solo/duo
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS participants (
    participant_id        TEXT PRIMARY KEY,     -- convention: f"{match_id}_{puuid}"
    match_id              TEXT NOT NULL REFERENCES matches(match_id),
    puuid                 TEXT NOT NULL,
    -- (v3) Riot's own 1-10 number for this participant within the match. The
    -- timeline keys every event and frame by it, not by puuid, so without it
    -- item_snapshots and participant_frames cannot be joined back to a row here.
    -- The draft's item_timing.py flagged the distinction but the schema never stored it.
    riot_participant_num  INTEGER NOT NULL CHECK (riot_participant_num BETWEEN 1 AND 10),
    champion              TEXT NOT NULL,
    role                  TEXT NOT NULL,        -- normalized team position, e.g. TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY
    team_id               INTEGER NOT NULL,     -- 100 or 200
    win                   INTEGER NOT NULL CHECK (win IN (0, 1)),
    UNIQUE (match_id, riot_participant_num)
);

CREATE INDEX IF NOT EXISTS idx_participants_match ON participants(match_id);
CREATE INDEX IF NOT EXISTS idx_participants_champion_role ON participants(champion, role);

CREATE TABLE IF NOT EXISTS item_snapshots (
    participant_id      TEXT NOT NULL REFERENCES participants(participant_id),
    snapshot_minute     INTEGER NOT NULL,       -- e.g. 10 or 15
    item_slot           INTEGER NOT NULL,       -- 0-6 (six item slots + trinket, per Riot's item layout)
    item_id             INTEGER NOT NULL,       -- 0 = empty slot
    PRIMARY KEY (participant_id, snapshot_minute, item_slot)
);

-- (v3) One row per participant per minute, from the timeline's participantFrames.
-- Two consumers: gold_diff_at_snapshot in the participant table (the confounder
-- #REC-1 has to control for), and the sequence model's input (#DL-7).
-- Filled by #FEAT-3's materialise step from the raw timeline JSON, using #FEAT-4.
CREATE TABLE IF NOT EXISTS participant_frames (
    participant_id          TEXT NOT NULL REFERENCES participants(participant_id),
    minute                  INTEGER NOT NULL,   -- 0 = game start
    total_gold              INTEGER NOT NULL,
    xp                      INTEGER NOT NULL,
    level                   INTEGER NOT NULL,
    minions_killed          INTEGER NOT NULL,
    jungle_minions_killed   INTEGER NOT NULL,
    PRIMARY KEY (participant_id, minute)
);

CREATE TABLE IF NOT EXISTS items_static (
    item_id     INTEGER NOT NULL,
    patch       TEXT NOT NULL,
    name        TEXT NOT NULL,
    gold_total  INTEGER,
    PRIMARY KEY (item_id, patch)
);

-- Not in the original Section 12 table, but needed by Functional Requirement #2
-- ("ingestion must checkpoint progress"). Kept as its own table rather than a
-- JSON file so a partially-ingested run can be queried with plain SQL.
CREATE TABLE IF NOT EXISTS ingestion_checkpoints (
    match_id     TEXT PRIMARY KEY,
    status       TEXT NOT NULL CHECK (status IN ('pending', 'done', 'failed')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
