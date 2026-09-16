# Phase 1 commissioning: manual, stopped-production test

This procedure is for an operator at the intended LJ3. Development has tested
the application offline only. Do not treat a successful TCP handshake or
matching readback as production acceptance.

**Stopped printing is our Phase 1 commissioning safety policy for the first
physical site test.** The supplied manuals do not say that ExternText can only
be changed while printing is stopped. Powered-on operation and protocol/font
rules are documented; the timing and effects of changes during active printing
remain unknown. Preserve this distinction when designing future Lot updates.

## Prepare the printer

1. Before assigning the reserved IP stored in local `.env`, verify with the
   site's network allocation records/administrator that it is still unused.
   A missing ping reply alone does not prove an address is free. Confirm the
   server's route to it uses the Machine NIC / factory Machine network.
   Configure the reserved IP on the intended Jet3. In Settings / Basic
   settings / IP_Adress, verify the IP and subnet mask. Under Extra / Interface
   settings / Connection Typ, select Ethernet and confirm the TCP port
   (the supplied manual uses 3000). Arrange server-to-printer routing/access
   with the site network configuration; the application changes none of this.
2. Power the printer on and take it out of standby using its local controls.
   Stop production and prevent print triggers during the text-change test.
   The application does not send power, nozzle, print-start, or print-stop
   commands and does not enforce a hardware interlock.
3. Load a suitable test job locally. It must contain an external-text object
   with `{e}` / EXTTXT, Field Number **0**, and a non-Unicode font (Unicode
   font names begin with `~`). Field Numbers 1 and 2 in the HyperTerminal
   manual are mailing fields and do not apply to this test.
4. Choose a known short ASCII value such as `BLUE`. For this four-character
   example, confirm that the object's character offset is 0 and its required
   placeholder count/length is appropriate for four characters. Check every
   Field 0 object: the largest offset-plus-placeholder count determines the
   job's required input. Never assume a readback proves all objects updated.
5. Check the job's **Check double prints** setting. When enabled, missing new
   ExternText can stop printing and raise an error; it is not automatically
   compatible with reusing the same color for an entire Lot. Establish the
   intended setting at the printer with the responsible operator.
6. Use normal unpadded interface output. The client can receive the optional
   five-digit length header but does not support fixed-block space padding.
   It does not enable/disable echo, length mode, CRC, or any other interface
   state. Resolve unexpected pre-existing modes through the printer/vendor;
   do not issue a factory reset to clear them as part of this procedure.
7. Ensure this test is the only controller changing ExternText. The protocol
   supplies no transaction IDs or protection against concurrent writers.

## Run the manual test

1. Start `.\.venv\Scripts\python.exe -m lj3` from the project. Confirm that
   startup displays the menu without a connection attempt.
2. Choose **1** and enter the verified printer IP, port, and timeout. A
   timeout of 3 seconds is application policy, not a printer requirement.
   Connect has this timeout; sending and waiting for a reply share a separate
   deadline of the same duration.
3. Choose **2**. Confirm the TCP connection opens and closes with no TX
   command. A reachable port alone could belong to another device.
4. Choose **4** to assess `?ET` support before changing text. Record the exact
   RX bytes and observed value. Expected ordinary framing is
   `^0=ET<value><CR>`; a length-prefixed response is also accepted. Old firmware
   may not support `?ET`. Timeout means no usable response, not proof of an
   empty value, rejected write, or unsupported command.
5. Choose **3** and enter the test value. Check the target, text, and byte
   preview. For `BLUE`, the entire frame must be:

   ```text
   Escaped: b'^0=ETBLUE\r'
   Hex:     5E 30 3D 45 54 42 4C 55 45 0D
   ```

   The final byte is CR, not the literal characters `\r`. The address is ASCII
   `0`, not byte `00`. There is no separator inserted before the text.
6. Confirm printing is stopped and the non-Unicode Field 0 test job is ready.
   Type **SEND** to send once, or anything else to cancel without network I/O.
   “Sent, UNVERIFIED” is expected. Normal ET writes need not return an ACK.
7. Choose **5**. This opens a fresh connection and sends only `^0?ET<CR>`.
   Check VERIFIED (exact readback)/MISMATCH and the exact returned text, including spaces.
   The manual's 20-40 ms reaction-time statement is not a guaranteed deadline;
   if needed, inspect the printer and manually perform another read later.
   The application never repeats a write to fix a mismatch.
8. Inspect the job display and, through the printer's normal local procedure,
   produce a controlled sample. Verify the correct object, visible color
   text, clipping/length, and intended layout. The application does not
   trigger this print. Return to stopped production before another write.
9. Record firmware, job name, font, Field 0 settings, double-print-check
   setting, tested value, TX/RX, measured response behavior, and physical
   result in the acceptance record below.

## Failure handling

- **Connection refused/timed out:** check the IP, Ethernet interface selection,
  port, network path, and printer mode. The tool does not reconnect by itself.
- **Send failed:** delivery is unknown. Do not immediately resend. Inspect the
  printer and use Read to determine the current value. Previous comparison
  history is cleared when a new write is attempted.
- **Read timeout/peer close:** the socket is closed. The next explicit action
  creates a new connection. No unsupported-command conclusion is inferred.
- **MISMATCH:** preserve raw logs and compare spaces, job font, length/offset,
  and concurrent writers. A Unicode hex payload is not automatically decoded.
- **Protocol error:** inspect the raw bytes. Wrong address, invalid length,
  controls, unexpected padding, malformed replies, or ambiguous coalesced
  replies fail closed. Do not bypass validation to make a response pass.
- **Printer error:** read its display. Unsolicited `=RS` errors and `=FC` CRC
  failures are reported. Other frames are shown without invented error
  meanings. This tool never acknowledges/clears a machine error automatically.

## Acceptance record (complete on site)

| Item | Observation |
| --- | --- |
| Date/operator | Pending |
| Printer identity/firmware | Pending |
| IP/port | Pending |
| Loaded job/font | Pending |
| Field 0 offsets/lengths | Pending |
| Double-print check | Pending |
| TCP connection test | Pending |
| `?ET` response format/support | Pending |
| Sent/readback comparison | Pending |
| Physical sample | Pending |
| Timeout/reconnect behavior | Pending |
| Approval to design production cutover | Pending |

Unicode, power-cycle/job-reload persistence, and changing text during active
production remain outside this Phase 1 acceptance. Obtain device/vendor
answers and controlled test results before designing Phase 2 Lot automation.
