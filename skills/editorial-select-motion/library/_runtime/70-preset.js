  /* preset: the replica layer. A block's PRESETS hold only motion and geometry
     (times, positions, scales, curves, slot rects); everything that belongs to
     the source (its words, traced glyphs, plate paths, sampled colours, per-shot
     calibration) lives outside the skill in work/replica/presets/<block>.json and
     arrives as props.replica. preset(PRESETS, props) returns the named preset
     with props.replica merged over it, props.replica alone when the block has no
     motion preset of that name, or null in general mode. Objects merge key by
     key; an array of objects merges element by element; anything else in the
     overlay replaces. */
  R.preset = (function () {
    function plain(v) { return v && typeof v === "object" && !Array.isArray(v); }
    function merge(a, b) {
      if (b === undefined) return a;
      if (Array.isArray(a) && Array.isArray(b) && b.length && b.every(function (x) { return plain(x) || x == null; })) {
        var out = a.slice(), n = Math.max(a.length, b.length);
        for (var i = 0; i < n; i++) out[i] = b[i] == null ? a[i] : merge(a[i], b[i]);
        return out;
      }
      if (plain(a) && plain(b)) {
        var o = {}, k;
        for (k in a) o[k] = a[k];
        for (k in b) o[k] = merge(a[k], b[k]);
        return o;
      }
      return b;
    }
    function preset(PRESETS, props) {
      var name = props && props.preset, base = name && PRESETS ? PRESETS[name] : null, over = props && props.replica;
      if (!name && !over) return null;
      if (!base && !over) return null;
      return base ? merge(base, over) : merge({}, over);
    }
    preset.merge = merge;
    return preset;
  })();
