# TEST CHECKLIST  (PASS-SIM = passed in simulation/mocks here; PI = must be confirmed on the Raspberry Pi)
Run simulation tests: `python3 -m unittest tests.test_aurora` (stubs pygame/google-genai; no hardware, no network).

| # | Subsystem / requirement | Simulation | On the Pi |
|---|---|---|---|
| 1 | Python syntax + imports of every module | PASS-SIM | NOT TESTED |
| 2 | Settings load; key never printed/logged | PASS-SIM | NOT TESTED |
| 3 | Aurora's visuals preserved (diff = +8 lines in face.py; other visual files identical) | PASS | NOT TESTED (visual) |
| 4 | Startup without camera / vosk / key / speaker / GPIO (each fails alone, report shows OFF) | PASS-SIM | NOT TESTED |
| 5 | INMP441 capture + VAD (algorithm replay on synthetic audio; read timeout; start failure) | PASS-SIM | **NOT TESTED** (`tools.check_mic`) |
| 6 | Mic independent of Bluetooth (no shared code; BT failure leaves mic loop alive) | PASS-SIM | NOT TESTED |
| 7 | Wake-word matching logic (word boundary, abort), fallback when model missing | PASS-SIM | **NOT TESTED** (real Vosk accuracy unknown) |
| 8 | No uncontrolled listening: without wake word or touch fallback nothing is ever sent | PASS-SIM | NOT TESTED |
| 9 | Gemini request/response parsing, emotion validation | PASS-SIM (fake client) | **NOT TESTED** (`tools.check_gemini`) |
| 10 | Gemini errors: 429/5xx/timeout/auth/empty → retry + spoken fallback, no crash, loop alive | PASS-SIM | NOT TESTED |
| 11 | Gemini TTS model fallback; empty audio = failure | PASS-SIM | **NOT TESTED** |
| 12 | Bluetooth sink resolution (right MAC only, no wired fallback), paced playback, disconnect mid-play | PASS-SIM (fake player) | **NOT TESTED** (`tools.check_bt_audio`) |
| 13 | Speech lifecycle: mouth starts after first write + latency, follows signal, closes when sound ends, rest state restored | PASS-SIM | **NOT TESTED** (judge by eye) |
| 14 | Overlapping speech: newest wins, no stale mouth events | PASS-SIM | NOT TESTED |
| 15 | Real `face.py` mouth override + original talk animation intact | PASS-SIM (pygame stubbed, `_update` logic) | **NOT TESTED** (rendering) |
| 16 | Touch gestures: single START, HOLD once, REPEAT, debounce | PASS-SIM | **NOT TESTED** (GPIO17/TTP223) |
| 17 | Touch → expression (shy/confused/angry, existing emotions), returns to baseline | PASS-SIM | NOT TESTED (visual) |
| 18 | Touch reacts while Gemini is blocked (no blocking) | PASS-SIM | NOT TESTED |
| 19 | State machine order listening→thinking→speaking→listening→idle; mic paused during speech | PASS-SIM | NOT TESTED |
| 20 | Camera optional: timeout-guarded, never blocks | PASS-SIM | NOT TESTED (camera still broken) |
| 21 | Graceful shutdown (worker ends, arecord stopped) | PASS-SIM | NOT TESTED (`./stop.sh`) |
