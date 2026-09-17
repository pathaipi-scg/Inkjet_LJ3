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
4. Use the fixed ASCII value `TEST123`. For this seven-character
   example, confirm that the object's character offset is 0 and its required
   placeholder count/length is appropriate for seven characters. Check every
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
2. Confirm the displayed target loaded from local `.env`. If a change is
   needed, choose **6 Configure Target** for session-only IP, port, and timeout.
   A timeout of 3 seconds is application policy, not a printer requirement.
   Connect has this timeout; sending and waiting for a reply share a separate
   deadline of the same duration. Configuration clears comparison history.
3. Choose **1 Test TCP Connection**. Expect **TCP CONNECTION OK** or
   **TCP CONNECTION FAILED**. The connection opens and closes with no LJ3
   command. A reachable port alone could belong to another device.
4. Choose **2 Read Current ExternText** before changing text. Record the exact
   RX bytes and value under `Current Jet3 ExternText:`. This sends only `?ET`.
   Expected ordinary framing is `^0=ET<value><CR>`; a length-prefixed response
   is also accepted. Old firmware may not support `?ET`. A timeout means no
   usable response, not proof of an empty value or unsupported command.
5. Choose **3 Send Test Text (TEST123)**. No text entry is needed. Check the
   target, `Text to send: TEST123`, and byte preview. The entire frame is:

   ```text
   Escaped: b'^0=ETTEST123\r'
   Hex:     5E 30 3D 45 54 54 45 53 54 31 32 33 0D
   ```

   The final byte is CR, not the literal characters `\r`. The address is ASCII
   `0`, not byte `00`. There is no separator inserted before the text.
6. Confirm printing is stopped and the non-Unicode Field 0 test job is ready.
   Type **SEND** to send once, or anything else to cancel without network I/O.
   **SENT - UNVERIFIED** is expected. Normal ET writes need not return an ACK.
7. Choose **4 Verify Last Sent Text**. This opens a fresh connection and sends
   only `^0?ET<CR>`. Check `Sent:`, `Jet3 Readback:`, and `Result:`. An exact
   match gives **VERIFIED**; a different value gives **MISMATCH**; failed
   communication or an invalid reply gives **COMMUNICATION ERROR**. Spaces
   matter; inspect escaped TX/RX logs when a difference is hard to see.
   The manual's 20-40 ms reaction time is not a guaranteed deadline. Inspect
   the printer and manually read again if needed. No write is retried.
   After **1 -> 2 -> 3 -> 4** passes, choose **5 Send Free Text**, enter
   `CHARCOAL GREY`, check the job lengths/offsets for this longer value, and
   confirm **SEND**. Then choose **4** again to verify the new value.
   Other ASCII examples: `RED`, `BLUE`, `COLOR A`, `LOT260917`.
8. Inspect the job display and, through the printer's normal local procedure,
   produce a controlled sample. Verify the correct object, visible color
   text, clipping/length, and intended layout. The application does not
   trigger this print. Return to stopped production before another write.
9. Record firmware, job name, font, Field 0 settings, double-print-check
   setting, tested value, TX/RX, measured response behavior, and physical
   result in the acceptance record below.

## Thai / Unicode experiment (blocked in this tool)

Prove ASCII communication and physical output first. Free Text detects
non-ASCII characters and displays **Unicode / Experimental - SEND BLOCKED**.
It does not request SEND confirmation, connect, or send UTF-8 or guessed hex.
Interface manual p.27 requires hexadecimal text for Unicode fonts configured
in the job; script manual p.25 identifies those fonts with `~`. The supplied
manuals do not fully define Unicode length limits or readback representation.
Confirm those rules, the installed Thai font/glyphs, and the job with the
vendor before arranging a separate controlled physical Unicode experiment.
A blocked entry leaves the last successfully submitted ASCII value available
for action **4** verification.

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
