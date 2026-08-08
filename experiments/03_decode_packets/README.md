# Experiment 03 - decode the packets

## What this proves

That the encrypted stream can be decrypted with a key derived from this
receiver's own serial number, and that the decrypted content is structured rather
than random.

This is Gate 4. Part A (decryption) passed. Part B (channel mapping) has not.

## Tools

### `decode.py` - find the key

Generates every documented AES key layout from the last four characters of the
USB serial, decrypts real packets with each, and scores them.

The score is the fraction of consecutive packets whose decrypted byte 0 advances
by one modulo 128. A wrong key gives noise, which scores under 3%. The right key
scores 100%. There is no ambiguity in the middle.

```sh
../../.venv/bin/python decode.py ../../captures/run007-linked.bin
```

Result on this hardware: `emokit_consumer (is_research=False)` at **100.00%**,
key `<32-hex-key-redacted----------->`. Everything else scored between 0.40% and
2.36% against an undecrypted baseline of 0.79%.

Note the naming trap: the winning layout is what **Emokit's code** calls consumer,
which is the same bytes **python-emotiv calls research**. The labels are
worthless; only the bytes matter. See RESEARCH.md section 4.1.

### `channels.py` - extract EEG channels

Applies Emokit's `sensors_14_bits` table and tests whether the result behaves
like EEG, using lag-1 autocorrelation.

Why that test: the EPOC is band-limited to roughly 0.16 to 43 Hz and sampled at
128 Hz, so consecutive samples of a real channel must be strongly correlated. A
wrong bit mapping gathers unrelated bits and scores near zero.

One adaptation for this hardware: Emokit indexes with `bits[i] // 8 + 1` because
it prepends a report-ID byte to make 33 bytes. Our interface declares no report
ID and hidapi gives us exactly 32, so we index with `bits[i] // 8`.

```sh
../../.venv/bin/python channels.py ../../captures/run007-linked.bin
```

Result: 0 of 14 channels above 0.9. **This is not yet a valid negative** - see
the caveat below.

### `scan_layout.py` - find the layout empirically

Rather than guessing another table, this slides a candidate field across every
bit offset in the packet and scores each by autocorrelation. It assumes nothing
about field order, channel names or where the payload starts.

```sh
../../.venv/bin/python scan_layout.py ../../captures/run007-linked.bin
../../.venv/bin/python scan_layout.py ../../captures/run007-linked.bin \
    --width 16 --threshold 0.30
```

Result: only byte 0 scored above 0.9, and that is the counter's sawtooth. At a
0.30 threshold one field stands out as interesting: 16 bits at offset 163
(byte 20, bit 3), mean 1185 with standard deviation 26.6, while every other
candidate swings across thousands. A narrow stable range is what a connected
channel looks like.

## The caveat that matters

The only capture so far was taken with the headset switched on but **not worn,
with dry electrodes**. The per-channel statistics show values railing between
about 30 and 16350, which is the signature of floating inputs, not EEG.

With no scalp contact there is no band-limited signal for the autocorrelation
test to detect. So the test currently **cannot distinguish a wrong bit table from
an absent signal**, and reporting "the Emokit table is wrong for this hardware"
would be overclaiming.

The fix is a better capture, not a bigger search: wet the felt pads with saline,
fit the headset properly, capture 60 seconds, and re-run both tools. With real
contact the autocorrelation test becomes decisive.
