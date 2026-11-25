# Practice table LAN checklist

## Start the host

1. On the Windows host, open the repository and run `Start Poker Coach.cmd`. For a test run, use a fresh temporary Coach database. In PowerShell, set `$env:COACH_DB_PATH = Join-Path $env:TEMP ('poker-lan-' + [guid]::NewGuid() + '.sqlite')` before starting.
2. Keep the launcher window open. Copy the LAN address it prints, including the port. Connect the second device to the same trusted Wi-Fi and open that address. The host can keep its own Coach tab open.

## Verify play and reconnection

1. On the second device, open **Practice table**. Start a table with an opponent name of **LAN test A** and leave the timer at 20 seconds.
2. Verify that the other seat visibly says **BOT**. Give it your normal phone orientation and try one legal sized action. The field expects the full street total. The timer starts again when your next action becomes available.
3. On another turn, wait for the timer. The table checks if checking is legal and folds if it faces a bet. Finish the hand and check that the Coach review appears.
4. Refresh the same browser tab. The practice page should open on the same table, with the same hand number and settlement if you refreshed after the hand finished.
5. Select **New table**, start **LAN test B**, and switch between the two table buttons. Make an action on B, then verify that A still has its own hand and outcome. Each table's timer runs while the other is selected.
6. Open **Review last session** on the completed table. When your play differs from the Coach's, the review lists that decision and its estimated cost when the solver's menu provides an EV. In **Coach → Saved data**, check that the hands appear under the names you entered.

## If a check fails

- If the page does not load, confirm the second device has the printed LAN address and is connected to the same network as the host. Try the printed address on the host before changing network settings.
- If the app asks you to wait after repeated requests, wait for the rate limit to clear. The Windows launcher shares a table creation limit across devices connected through its local proxy. Existing tables have their own request limits.
- A refresh can recover the seat in the same browser tab while the server is running. A closed table, an idle table that expired, or a server restart ends the associated seat. Completed hands remain in Coach.
- Press Enter in the launcher window after testing to stop both services.
