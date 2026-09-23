# Memory

A Jev-Mem memory server is connected. It holds durable knowledge from earlier
sessions and is separate from this repository's contents.

- Before answering anything that depends on an earlier session -- a stated
  preference, a past decision and its reason, a constraint we agreed on --
  call `memory_recall` first. Do not guess, and do not claim there is no record
  without having called it.
- `memory_recall` returns evidence, not an answer. Read the observations and
  write the answer yourself. If the evidence does not cover the question, say so.
- When something durable is established -- a decision, a constraint, a
  preference, a fact about this project or the person -- call `memory_remember`
  with one self-contained sentence. Phrase it so it still makes sense months
  from now without this conversation.
- Do not store transient conversation detail, secrets, or anything already in
  the repository. The code and its history are already available to you.
