// db.js — open a single shared SQLite connection using Node's built-in module.
// node:sqlite (stable since Node 24) needs no npm package or C++ compilation.

import { DatabaseSync } from 'node:sqlite'
import { dirname, join } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const DB_PATH   = join(__dirname, '..', 'bgg.db')

const db = new DatabaseSync(DB_PATH, { readOnly: true })

export default db
