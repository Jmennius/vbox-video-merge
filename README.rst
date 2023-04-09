VBox video merge
================

This script inserts a reference to the video into a VBox (``.vbo``) telemetry file.

Resulting VBox file can be opened and analyzed in `RaceLogic Circuit Tools 2`.


Prerequisites
-------------

Video file should be in the same directory as vbox file,
video filename should start with alpha prefix followed by a number and end with ``.MP4`` extension.


Working configuration
---------------------

This was used successfully with a vbox file exported by `racebox`
and a video recorded with Sony FDR-X3000 (FullHD 60fps HEVC).


TODO/ideas
----------

* It is possible to automatically find video synchronization offset (at least approximate offset)
  by looking at video metadata and comparing that to what is in vbox (assuming the camera has GPS enabled?).
* We should be able to automatically match VBox files to video files as well (timestamps in video metadata + vbox ``time``).
