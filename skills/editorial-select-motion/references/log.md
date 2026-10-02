# Log

{{Dated entries: the piece, the miss, what caught it (metric, judge or Umer), and the token, element, rule or band that was changed so it cannot recur.}}

2026-10-02. Tempo was recorded as 136 BPM from `toolkit/music.py`; building the sound truth file showed the track is 140.3 BPM (bar 1.711 s), measured by comparing each bar with the bars either side. The 136 reading put every two-bar comparison about 100 ms off. Corrected in scenes.md, delivery.md and sound.md; music.py's tracker needs the same fix so the next style does not inherit it.

2026-10-02. Building the icon-tile and giant-type-pass blocks, the giant pass rendered five frames late in the composed proof (compare.py global offset and SSIM 0.936). icon-tile placed its first steps half a frame early at t0 = 0, which is a negative time, and a GSAP timeline that receives a child before zero shifts every child already on it later: ten nodes at -0.0208 s moved the block added before it by 0.208 s. Both blocks now clamp every step to time zero. Any element that leads a frame must do the same; the rule belongs in ~/motion-ui/library/CONTRACT.md next to the immediateRender note.
