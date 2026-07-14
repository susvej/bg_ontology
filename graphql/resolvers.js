// resolvers.js
//
// A resolver is a function that returns the data for one field in the schema.
// GraphQL calls resolvers lazily: it only fetches data you actually asked for.
//
// Resolver signature: (parent, args, context, info)
//   parent — the object returned by the parent resolver (e.g. a Game row)
//   args   — arguments from the query  (e.g. { limit: 10, category: "Fantasy" })

import db from './db.js'

// ── Prepared statements (compiled once at startup, reused on every request) ───
const stmts = {
  gameById: db.prepare(
    `SELECT * FROM games WHERE id = ?`
  ),

  categoriesOfGame: db.prepare(
    `SELECT c.* FROM categories c
     JOIN game_categories gc ON gc.category_id = c.id
     WHERE gc.game_id = ?`
  ),
  mechanicsOfGame: db.prepare(
    `SELECT m.* FROM mechanics m
     JOIN game_mechanics gm ON gm.mechanic_id = m.id
     WHERE gm.game_id = ?`
  ),
  creatorsOfGame: db.prepare(
    `SELECT c.* FROM creators c
     JOIN game_creators gc ON gc.creator_id = c.id
     WHERE gc.game_id = ?`
  ),
  publishersOfGame: db.prepare(
    `SELECT p.* FROM publishers p
     JOIN game_publishers gp ON gp.publisher_id = p.id
     WHERE gp.game_id = ?`
  ),

  // expansion_id = the expansion game, base_id = the base game
  expandedBy: db.prepare(
    `SELECT g.* FROM games g
     JOIN game_expansions ge ON ge.expansion_id = g.id
     WHERE ge.base_id = ?`
  ),
  expandsTo: db.prepare(
    `SELECT g.* FROM games g
     JOIN game_expansions ge ON ge.base_id = g.id
     WHERE ge.expansion_id = ? LIMIT 1`
  ),

  // newer_id = the reimplementation, older_id = the original
  reimplementedBy: db.prepare(
    `SELECT g.* FROM games g
     JOIN game_reimplements gr ON gr.newer_id = g.id
     WHERE gr.older_id = ?`
  ),
  reimplements: db.prepare(
    `SELECT g.* FROM games g
     JOIN game_reimplements gr ON gr.older_id = g.id
     WHERE gr.newer_id = ? LIMIT 1`
  ),

  allCategories: db.prepare(`SELECT * FROM categories ORDER BY id`),
  allMechanics:  db.prepare(`SELECT * FROM mechanics ORDER BY id`),

  gamesByCategory: db.prepare(
    `SELECT DISTINCT g.* FROM games g
     JOIN game_categories gc ON gc.game_id = g.id
     WHERE gc.category_id = ?
     ORDER BY g.geek_rating DESC LIMIT ?`
  ),
  gamesByMechanic: db.prepare(
    `SELECT DISTINCT g.* FROM games g
     JOIN game_mechanics gm ON gm.game_id = g.id
     WHERE gm.mechanic_id = ?
     ORDER BY g.geek_rating DESC LIMIT ?`
  ),

  creatorById:    db.prepare(`SELECT * FROM creators WHERE id = ?`),
  gamesOfCreator: db.prepare(
    `SELECT g.* FROM games g
     JOIN game_creators gc ON gc.game_id = g.id
     WHERE gc.creator_id = ?
     ORDER BY g.geek_rating DESC`
  ),

  allPlayers:       db.prepare(`SELECT * FROM players ORDER BY label LIMIT ? OFFSET ?`),
  playerById:       db.prepare(`SELECT * FROM players WHERE id = ?`),
  gamesOwnedBy:     db.prepare(
    `SELECT g.* FROM games g
     JOIN player_owns po ON po.game_id = g.id
     WHERE po.player_id = ?
     ORDER BY g.geek_rating DESC`
  ),
  opinionsOfPlayer: db.prepare(
    `SELECT * FROM player_opinions WHERE player_id = ?`
  ),
}

// ── Query resolvers (top-level entry points) ──────────────────────────────────
const Query = {
  game(_, { id }) {
    return stmts.gameById.get(id) ?? null
  },

  games(_, { limit = 20, offset = 0, name, minRating, category, mechanic }) {
    // Build SQL dynamically — only JOIN and WHERE what the caller asked for.
    // This is a key GraphQL pattern: flexible filtering without over-fetching.
    let sql    = `SELECT DISTINCT g.* FROM games g`
    const params = []
    const where  = []

    if (category) {
      sql += ` JOIN game_categories gc ON gc.game_id = g.id`
      where.push(`gc.category_id = ?`)
      params.push(category)
    }
    if (mechanic) {
      sql += ` JOIN game_mechanics gm ON gm.game_id = g.id`
      where.push(`gm.mechanic_id = ?`)
      params.push(mechanic)
    }
    if (name) {
      where.push(`g.name LIKE ?`)
      params.push(`%${name}%`)
    }
    if (minRating != null) {
      where.push(`g.geek_rating >= ?`)
      params.push(minRating)
    }

    if (where.length) sql += ` WHERE ` + where.join(` AND `)
    sql += ` ORDER BY g.geek_rating DESC LIMIT ? OFFSET ?`
    params.push(limit, offset)

    return db.prepare(sql).all(...params)
  },

  categories() { return stmts.allCategories.all() },
  mechanics()  { return stmts.allMechanics.all() },

  creator(_, { id })                { return stmts.creatorById.get(id) ?? null },
  creators(_, { name, limit = 20 }) {
    if (name) {
      return db.prepare(
        `SELECT * FROM creators WHERE label LIKE ? ORDER BY label LIMIT ?`
      ).all(`%${name}%`, limit)
    }
    return db.prepare(`SELECT * FROM creators ORDER BY label LIMIT ?`).all(limit)
  },

  player(_, { id })                      { return stmts.playerById.get(id) ?? null },
  players(_, { limit = 20, offset = 0 }) { return stmts.allPlayers.all(limit, offset) },
}

// ── Game field resolvers ──────────────────────────────────────────────────────
// These only fire when the client explicitly requests that field.
// If you query { game(id:"1") { name } }, none of the nested resolvers below run.
const Game = {
  // Rename snake_case DB columns to camelCase GraphQL fields
  geekRating:     (g) => g.geek_rating,
  minPlayers:     (g) => g.min_players,
  maxPlayers:     (g) => g.max_players,
  bestNumPlayers: (g) => g.best_num_players,
  minTime:        (g) => g.min_time,
  maxTime:        (g) => g.max_time,
  minRecAge:      (g) => g.min_rec_age,

  // Nested lists — each fires a separate SQL query
  categories:      (g) => stmts.categoriesOfGame.all(g.id),
  mechanics:       (g) => stmts.mechanicsOfGame.all(g.id),
  creators:        (g) => stmts.creatorsOfGame.all(g.id),
  publishers:      (g) => stmts.publishersOfGame.all(g.id),
  expandedBy:      (g) => stmts.expandedBy.all(g.id),
  expandsTo:       (g) => stmts.expandsTo.get(g.id) ?? null,
  reimplementedBy: (g) => stmts.reimplementedBy.all(g.id),
  reimplements:    (g) => stmts.reimplements.get(g.id) ?? null,
}

// ── Category / Mechanic resolvers ─────────────────────────────────────────────
const Category = {
  games: (cat, { limit = 10 }) => stmts.gamesByCategory.all(cat.id, limit),
}
const Mechanic = {
  games: (mech, { limit = 10 }) => stmts.gamesByMechanic.all(mech.id, limit),
}

// ── Creator resolvers ─────────────────────────────────────────────────────────
const Creator = {
  games: (creator) => stmts.gamesOfCreator.all(creator.id),
}

// ── Player resolvers ──────────────────────────────────────────────────────────
const Player = {
  owns: (player) => stmts.gamesOwnedBy.all(player.id),

  opinions: (player) => {
    const rows = stmts.opinionsOfPlayer.all(player.id)
    // Stash the game_id so Opinion.game can look it up
    return rows.map(r => ({
      gameId:    r.game_id,
      rating:    r.rating,
      mentalLoad: r.mental_load,
    }))
  },

  // Likes are stored in fake_players.ttl, not yet in SQLite.
  // Exercise for later: load them into the DB and wire these up.
  likesCategories: () => [],
  likesMechanics:  () => [],
}

// ── Opinion resolver ──────────────────────────────────────────────────────────
const Opinion = {
  game: (opinion) => stmts.gameById.get(opinion.gameId) ?? null,
}

export default { Query, Game, Category, Mechanic, Creator, Player, Opinion }
