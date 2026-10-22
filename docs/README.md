# Documentation

Project documentation lives in this folder. It is part of the repository, so
every document is versioned with the code it describes and travels with a
clone, an export or a publish.

Suggested layout — add only what the project actually needs:

| File | Content |
|------|---------|
| `overview.md` | What the product does, for whom, and the main flows |
| `architecture.md` | Components, data flow, and why it is built this way |
| `data-model.md` | Entities, relations, and the meaning of key fields |
| `api.md` | Endpoints, request/response shapes, error cases |
| `operations.md` | Environments, deployment, and known limitations |
| `decisions.md` | Decisions worth remembering, newest first |

Two rules:

- **No credentials.** Environment variables belong in the Environment tab —
  name them here, never paste values.
- **Documents describe the current state.** Update the page that is wrong
  instead of appending a changelog to it.

Ask the AI in the chat to write or update documentation — it reads and writes
files in this folder directly.
