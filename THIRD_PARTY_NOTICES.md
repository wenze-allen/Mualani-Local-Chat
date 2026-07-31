# Third-party notices

[简体中文](THIRD_PARTY_NOTICES.zh-CN.md)

## llama.cpp

The runtime is a downstream text-only build of
[llama.cpp](https://github.com/ggml-org/llama.cpp), pinned to commit
`e9fa0781f1c25fc4fe8c86be1edc6970661ad6f0` and modified through the files in
`overlay/`.

llama.cpp is licensed under the MIT License. Its license text is reproduced in
[`licenses/llama.cpp-MIT.txt`](licenses/llama.cpp-MIT.txt).

## Model weights

Model weights are not part of the source tree or the Linux/Windows application
archives. Compatible Mualani GGUF shards are published as separate GitHub
Release assets and are derived from the Huihui Qwen3.5 4B and 9B models. The
model repository identifies the base models as Apache-2.0. Review the model
card and all upstream terms before redistributing weights:

- <https://huggingface.co/Allen0204/Mualani-Qwen3.5-LoRA-GGUF>
- <https://huggingface.co/huihui-ai/Huihui-Qwen3.5-4B-abliterated>
- <https://huggingface.co/huihui-ai/Huihui-Qwen3.5-9B-abliterated>

## Reference material

The runtime cards contain concise factual summaries and behavioral constraints;
the complete research cards additionally retain short evidence records and
revision references. The research process used the Genshin Impact Wiki on
Fandom as the principal public reference and BWiki for cross-language
verification. Fandom community text is generally published under CC BY-SA 3.0.
Attribution and source links are listed in [`SOURCES.md`](SOURCES.md). No game
audio, complete dialogue corpus, generated training split, checkpoint, or wiki
article mirror is shipped in this repository.

## Fan-project notice

This is an unofficial, non-commercial fan and research project. It is not
endorsed by or affiliated with HoYoverse, miHoYo, or Cognosphere. Genshin
Impact, its characters, names, and related game content belong to their
respective rights holders.
