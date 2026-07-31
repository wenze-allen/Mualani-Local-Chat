# Contributing

Small, reviewable fixes are welcome. Please keep the runtime text-only and do
not add training data, game audio, copied dialogue, model weights, or private
research logs.

Create a branch in your fork, push the change there, and open a pull request
against `main`. Direct pushes to `main` are review-protected; a pull request
needs one approving review and all review conversations resolved before merge.

For code changes:

1. Build the Linux or Windows package using the documented script.
2. Run `llama-cli --list-devices` and a short CPU smoke test.
3. If changing cards, keep only fields consumed by the runtime and state the
   public factual basis in the change description.
4. Do not commit GGUF files or generated build directories.

Security-sensitive reports should not include tokens, private model URLs, or
conversation histories.
