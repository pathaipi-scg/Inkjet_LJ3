# Phase 1 commissioning: manual, stopped-production test

This procedure is for an operator at the intended LJ3. A read-only status and
ExternText communication diagnostic and exact `TEST123` readback have been
completed; physical job rendering/print output and production acceptance remain
untested. Do not treat a successful TCP handshake or matching readback as
production acceptance.

An `=ET` write followed by `?ET` is a communication-only test: a Field 0
object and verified job offsets/placeholder lengths are not required. The write
does change the printer's ExternText value, so keep printing stopped, inhibit
print triggers, and ensure there is no competing ExternText writer. Do not
modify the loaded job for this test. Field 0 integration and physical printing
are separate tests and remain unverified until explicitly performed.

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
   The application can query status with read-only `?RS`, but it does not
   change printer state or enforce a hardware interlock. It does not send
   power, nozzle, print-start, or print-stop commands.
3. Do not modify the current print job for a communication-only test. A
   suitable Field Number **0** external-text object (`{e}` / EXTTXT) with a
   non-Unicode font (Unicode font names begin with `~`) is needed only for a
   separate print-integration test. Field Numbers 1 and 2 in the HyperTerminal
   manual are mailing fields and do not apply to this test.
4. Use the fixed ASCII value `TEST123` for the first communication-only write.
   For a later print-integration test, confirm that the relevant Field 0
   object's character offset is 0 and its placeholder count/length covers
   seven characters. Check every Field 0 object: the largest
   offset-plus-placeholder count determines the job's required input. These
   job checks are not required for `=ET`/`?ET` testing. A readback does not
   prove that print-job objects updated.
5. For a separate physical print-integration test, review the job's **Check
   double prints** setting with the responsible operator. When enabled, missing
   new ExternText can stop printing and raise an error; it is not automatically
   compatible with reusing the same color for an entire Lot. This setting is
   not a prerequisite for communication-only `=ET`/`?ET` testing.
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
   The default timeout is 10 seconds, an application setting rather than a
   printer requirement. Configuration clears comparison history and closes the
   current session.
3. Choose **1 Test TCP Connection**. Expect **TCP CONNECTION OK** or
   **TCP CONNECTION FAILED**. No LJ3 command is sent. A successful connection
   remains open for later sequential menu actions and closes on quit,
   reconfiguration, or communication/protocol failure. A reachable port alone
   could belong to another device.
4. Choose **2 Read Current ExternText** before changing text. Record the exact
   RX bytes and value under `Current Jet3 ExternText:`. This sends only `?ET`.
   Expected ordinary framing is `^0=ET<value><CR>`; a length-prefixed response
   is also accepted. Old firmware may not support `?ET`. A timeout means no
   usable response, not proof of an empty value or unsupported command.
5. Optionally choose **7 Read Printer Status** to send read-only `?RS`. The
   display labels the five documented `=RS` parameters (nozzle, machine state,
   error, headcover, ActSpeed) and shows any additional parameters as opaque
   bytes without assigning meanings. Raw RX bytes/hex and elapsed response
   time are logged. This does not change printer state.
6. Choose **3 Send Test Text (TEST123)**. No text entry is needed. Check the
   target, `Text to send: TEST123`, and byte preview. The entire frame is:

   ```text
   Escaped: b'^0=ETTEST123\r'
   Hex:     5E 30 3D 45 54 54 45 53 54 31 32 33 0D
   ```

   The final byte is CR, not the literal characters `\r`. The address is ASCII
   `0`, not byte `00`. There is no separator inserted before the text.
7. Confirm printing is stopped, print triggers are inhibited, and no other
   controller is writing ExternText. The application requires confirmation
   of these conditions. It also requires confirmation that optional `!EM`
   command echo is disabled; otherwise an echoed write frame on the same
   connection could be mistaken for the readback. The app does not detect or
   change `!EM`. Field 0 integration is not required for this communication
   test. Type **SEND** to confirm the write-safety conditions, then **ECHO OFF**
   only if echo is confirmed disabled; otherwise cancel. **SENT - UNVERIFIED**
   is expected. Normal ET writes need not return an ACK. No automatic retry.
8. Choose **4 Verify Last Sent Text**. It sends `^0?ET<CR>` on the same still-
   open TCP connection used for the write. It refuses to reconnect if that
   session was lost. Check the exact `repr` values for sent/readback text and
   `Result:`. An exact
   match gives **VERIFIED**; a different value gives **MISMATCH**; failed
   communication or an invalid reply gives **COMMUNICATION ERROR**. Spaces
   matter; inspect escaped TX/RX logs when a difference is hard to see.
   The manual's 20-40 ms reaction time is not a guaranteed deadline. Inspect
   the printer and manually read again if needed. No write is retried.
   After **1 -> 2 -> 3 -> 4** passes, choose **5 Send Free Text**, enter
   `CHARCOAL GREY`, and confirm **SEND** and **ECHO OFF**. Then choose **4**
   again to verify the new value. Length/offset checks are needed only before
   separately testing Field 0 print integration, not for this communication test.
   Other ASCII examples: `RED`, `BLUE`, `COLOR A`, `LOT260917`.
9. **Separate physical print-integration test; not part of communication
   validation.** Only after separate authorization and Field 0 integration
   preparation, inspect the job display and use the printer's normal local
   procedure to produce a controlled sample. Verify the correct object,
   visible text, clipping/length, and intended layout. The application does
   not trigger printing. This step remains **NOT TESTED** for the current
   communication milestone.
10. Record firmware, job name, font, Field 0 settings, double-print-check
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
   port, network path, and printer mode. A failed operation is not automatically
   retried. A later operator action may open a new session.
- **Send failed:** delivery is unknown. Do not immediately resend. Inspect the
   printer and use a read-only inquiry to determine the current value. A new
   write attempt invalidates prior verification history.
- **Read timeout/peer close:** the affected session is closed; the failed
   operation is not retried. A later explicit read action may open a new
   session, but action 4 will not reconnect or claim same-session verification
   after a write.
- **MISMATCH:** preserve raw logs and compare spaces, job font, length/offset,
   and concurrent writers. A Unicode hex payload is not automatically decoded.
- **Protocol error:** inspect the raw bytes. Wrong address, invalid length,
   controls, unexpected padding, malformed replies, or ambiguous coalesced
   replies fail closed. Do not bypass validation to make a response pass.
- **Printer error:** read its display. `=FC` CRC failures and `=RS` numeric
   status fields are reported; other frames are shown without invented error
   meanings. The tool never acknowledges or clears a machine error automatically.

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
