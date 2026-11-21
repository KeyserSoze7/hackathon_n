# MARG demo video: script (target 2:00, cut to 1:30 by dropping the lines marked [cut])

Frames come from the running frontend (screen recording of `http://localhost:5173` on a 390 × 844 phone view for the citizen scenes, and a 1280 × 720 laptop view for the officer scenes). Numbers are read live from the backend; confirm them on screen before recording.

| Time | On screen | Voice-over |
|---|---|---|
| 0:00 – 0:08 | Boot animation, the MARG emblem forms with "हर रुपये का हिसाब". | Every monsoon, Mumbai spends crores fixing the same roads. Nobody can easily say where the money went, whether the fix lasted, or where the next rupee should go. This is MARG. |
| 0:08 – 0:25 | **Find a road**, phone view. Type "Andheri subway ke bahar khadda ho gaya". The match card appears: road, ward, warranty status, billed amount. | A citizen types a landmark, in any language they use. MARG finds the road and shows what was billed there, whether it is still under the contractor's warranty, and how many bills need an explanation. No login, no app. |
| 0:25 – 0:55 | Tap **Report a problem on this road**. Step through What, Photo, Where, Review. Send. The tracker fills: report received, matched to contract, payment held. | If the road is broken again, the citizen reports it in four taps: what is wrong, a photo, where, and send. The report is matched to the road and its contract. If the road is under warranty, the bill is flagged and the contractor, not the public, owes the repair. And the citizen can watch it move. |
| 0:55 – 1:15 | **Road receipt** for Kurla Andheri Road, laptop view. Scroll the proof trail: complaint, repair, failures, audit flags. Open the evidence rows and show the row IDs. | Behind every answer is a receipt. Thirty-five jobs on one stretch of Kurla Andheri Road, eight flagged bills, each with its rule and its evidence IDs, so anyone can verify it. Flags say "needs explanation", never "fraud", and the ward engineer or contractor can reply on the record. |
| 1:15 – 1:35 | **City audit.** Hero headline, ₹13.43 Cr spent, ₹60.3 lakh billed under warranty, 527 bills needing explanation. Click a ward on the map; the flagged cards filter. | For the city: 13.43 crore spent, 60.3 lakh of it billed on roads still under warranty, and 527 bills that need explaining, from warranty to overlapping work orders to rain-day work. Select any ward and see exactly which bills. |
| 1:35 – 1:50 | **Contractors**, then **Next rupee**. Show one contractor card (Deccan: 9.1% failed against 22.9% expected, "better than expected"). Move the budget slider in **Next rupee**; the funded list changes and the ₹0 warranty box stays. | Contractors are judged fairly: each failure rate sits next to what the rain, tides and roads predict, so nobody is punished for working in a flood-prone ward. And the next rupee goes where it does the most good. Roads under warranty cost the city nothing, so that money moves to the roads that need it. |
| 1:50 – 2:00 | Return to the emblem, tagline. | Where did the money go? Did the fix last? Where should the next rupee go? MARG answers all three. Har rupaye ka hisaab. |

## Cuts for 1:30

- Drop the 0:55 – 1:15 road-receipt scene's evidence-row detail; keep one sentence on the receipt.
- Merge Contractors and Next rupee into one 10-second shot: contractor verdict, then the slider.
- Shorten the opening to 5 seconds.

## Notes for recording

- Honest framing: the data is synthetic, and the photo step previews the photo but does not upload it yet. Say "photo upload is coming" if asked; do not claim it is sent.
- The signboard and QR options are demos. Show the typed lookup instead.
- Record the citizen scenes on a real phone or a 390 px browser window; the bottom navigation should be visible.
- The Hindi and Marathi toggle only translates the navigation. Do not demonstrate full translation.
- Delete the "FRONTEND TEST" reports (ids 6 to 9) before recording so the demo data is clean.
