# Product FAQ

## What is this service?

This is an AI-powered chat backend that uses Groq for fast inference and supports a configurable knowledge base. You can add markdown or text files in the `data` folder to give the assistant domain-specific context.

## How do I get an API key?

Sign up at [Groq](https://console.groq.com/) and create an API key. Set it in your environment as `GROQ_API_KEY`.

## Session memory

Each conversation is tied to a `session_id`. Send the same `session_id` in your chat requests to keep context. Create a new session with `POST /sessions/new` or use any string as `session_id`; the first message with that id will create the session.
