# B2 browser verification

Scratch app at `http://127.0.0.1:18012/`, using the production frontend build and one synthetic logged hand in a temporary SQLite database.

| Check | Observed in the in-app browser |
| --- | --- |
| Phone width | Requested 390 × 844. Document client and scroll widths were both 375 px. |
| Keyboard setup | Entered Sandbox Rival, pressed P, and typed As Kd. Coach started in the big blind and showed the opponent's turn. |
| Recent size | **Recent 375** appeared. One click recorded **Villain: Raise to 375** and offered **Call 275**. |
| Board and undo | C called. Typed 7h 8d 2c to reach the flop. Z returned to the flop entry, and typing the same board again returned the hero decision. |
| Typed amount and settlement | C checked. Typed 200 and Enter for the opponent, saw Call 200, and pressed F. The activity showed **Villain: Bet 200**, **You folded**, and the result of **−375**. |
| Next hand | N returned to setup with **Pick 2 more cards**. |
| Browser console | Zero error messages. Viewport reset after testing. |

The branch includes the frontend type check, two Node tests and build output in `coach-frontend.log`.
