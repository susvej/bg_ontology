// index.js — Apollo Server entry point
//
// Apollo Server 4 uses the "standalone" HTTP server by default.
// It serves:
//   http://localhost:4000/      → GraphQL endpoint (for programmatic queries)
//   http://localhost:4000/      → Apollo Sandbox (interactive browser IDE)
//
// The Sandbox gives you autocomplete, inline docs, and query history —
// the best way to explore the schema hands-on.

import { ApolloServer }        from '@apollo/server'
import { startStandaloneServer } from '@apollo/server/standalone'
import { readFileSync }         from 'fs'
import { dirname, join }        from 'path'
import { fileURLToPath }        from 'url'
import resolvers                from './resolvers.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const typeDefs  = readFileSync(join(__dirname, 'schema.graphql'), 'utf8')

const server = new ApolloServer({ typeDefs, resolvers })

const { url } = await startStandaloneServer(server, {
  listen: { port: 4000 },
})

console.log(`
  GraphQL server running at ${url}
  Open that URL in your browser for the Apollo Sandbox playground.
`)
