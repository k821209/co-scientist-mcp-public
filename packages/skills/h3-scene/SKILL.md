---
name: h3-scene
description: Build a generated video scene chunk by chunk with the vh.h3 pipe (MiniMax-H3 via ComfyUI, Krea2 keyframes) against the Video tab's chunk rows — boundaries first, the user's GO, then only the approved chunks, then the join. Use when the user asks for a generated scene, a multi-shot clip, "청크로 장면 만들기", or names H3 / Krea.
---

# /h3-scene

> **Needs** the video tool family (see `/video-revision`'s note) and `vh`
> installed with `VH_H3_*` set for this machine — read
> `vh/h3/README.md` §7 in the vh checkout; every machine constant is an
> environment variable and none is hardcoded. `python -m vh.h3.h3_scene
> --help` refusing with a `VH_H3_HOME` message means the env is not set.

**What it solves.** Chaining generated chunks by passing each one's last
frame into the next accumulates tone and contrast. The pipe draws each
boundary as a Krea2 keyframe from the START image and shares that one
picture as the previous chunk's last and the next chunk's first — no
accumulation path, and the seam cannot mismatch. The numbers behind every
threshold and rule are in the README §4–§6; they were set by a user watching
the raw chunks, not by a model.

## The boundary — agent vs script

The script runs on the GPU machine and **cannot reach the MCP**. So the
script never decides which image a chunk starts from; it takes `--first` /
`--last` paths and stages them by content hash. **The row in the Video tab
is the truth**, and the agent carries files between the two:

```
agent (MCP)                                  script (vh.h3)
add_video(title, aspect_ratio)          
add_video_chunk(n, prompt, continuous)  
                                        →    h3_scene boundaries --shots cfg.json --out <name>
update_video_chunk(n, last_image=B_n)   ←    manifest after ###JSON###
   … user judges keyframes in the tab, turns GO on; STOP here …
get_video_chunk_image(n, which="start") 
get_video_chunk_image(n, which="last")  
                                        →    h3_scene chunk --n n --first <path> --last <path>
add_video_chunk(n, prompt, local_path=) ←    result path after ###JSON###
                                        →    h3_scene join --parts a,b,c        (only when asked)
join_video_chunks(local_path=)          ←
```

The order and the gate are `project_guide()`'s "Generated video, chunk by
chunk" list; this skill adds only what is specific to the script.

## Specific to the script

- **Config** is one JSON per scene (`vh/h3/configs/*.json` are real ones:
  cafe 5 chunks, park bench 3, running selfie 3). Read one before writing a
  new one; the prompt rules read faster as examples than as prose.
- **Parse only the line after `###JSON###`.** Everything else is progress.
- **Row `n` is the tab's 1-based number; the script's chunk index is
  `n - 1`.** `--n` takes the tab's number.
- **Always pass `--first` from `get_video_chunk_image(..., which="start")`
  fetched right before the call**, and `--last` from `which="last"`. Never
  a local PNG picked by name: the README §3 case (a stale `_b3.png`) cost
  five minutes per wrong chunk.
- **Checks** (`sparkle`, `tailjump`, `motion`) retry with a new seed on
  their own; record the returned `metrics` on the row via `add_video_chunk
  (metrics=)`. A moving scene overrides the thresholds in its config (see
  `run.json`) — and after generation, look at the filmstrip
  (f0/f24/f48/f72/f96/f123): the checks cannot see a back-and-forth motion
  or a background element that appears and vanishes.
- **Seams:** nothing by default; `trim_settle`/`trim_head` are the only
  knobs. No crossfade, no fade-to-black — both measured worse.
- **Join** goes on the same video (`join_video_chunks(local_path=)`), never
  a chunk row, never a second video.

## When something is off

A jump at a seam → compare the tab's "last" (aimed) and "ended" (actual)
thumbnails of the previous row; regenerate from `which="start"` again after
the previous file is registered. A chunk that runs in place → the boundaries
share a background; move each to a different stretch (README §4 rule 6).
