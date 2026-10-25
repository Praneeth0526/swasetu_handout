# Officer Briefing Note: Deputy Commissioner, Sonapur District

**Audio Source:** `dc-briefing.mp3`  
**Speaker:** Deputy Commissioner (IAS), Sonapur District, Purvanchal  
**Role:** In-charge of Sewa Setu Old Age Pension Portal  
**Context:** Handover / Briefing to Digital Fellow (Build for Bharat 2027)

---

## Verbatim Audio Transcript

**Speaker: Deputy Commissioner (DC)**

> "Namaste. I am the Deputy Commissioner in charge of Seba Setu, the IT platform for old age pension. So, you are the one they have sent from Build for Bharat Fellowship? Good. Sit, sit. You will have to forgive me. I do not have a file to hand you. The vendor who built the Seba Setu portal, their contract ended, and now nobody picks up the phone. Documentation? I do not think we ever got any. So let me just tell you what's landed on my desk this past week and whatever else comes to mind.
> 
> First, an old man walked 2 hours from his village just to show me his acknowledgement slip, and where his name should be, in Assamese, it shows four question marks. Four. He swears he typed it correctly, and I believe him because he's not the first. Others tell me their names come out cut in half, but they swear they typed it in full before submitting.
> 
> Then there's my helpdesk overflowing—people writing in begging us to cancel their application because they made one small mistake, realized it only after submitting, and then found there is no way to fix it. No way to go back. We delete requests, and then they submit again.
> 
> Now, before you look at the machine, you need to understand the law. There is the Right to Public Services Act. We call it RTPS. It promises every citizen a decision within a set number of days. And if we stay silent past that window, if we just sit on it, the application is deemed approved. The law says yes on our behalf, and that pension becomes the person's right. For this scheme, that window is 15 days. For years, the overdue files used to clear themselves overnight, the moment they crossed the line. Then, around Holi, it just stopped. Now, files the Act says should be auto-approved are sitting for months, and the appellate officer has started asking me why. I am going to be in trouble over this one.
> 
> And another thing. Every month, the two or three days before the disbursement deadline, the whole site crawls to a halt. My staff just shrug. "Server slowdown hai, sir. Kya karenge?" It recovers, of course, the day after it stops mattering. See what is going on there.
> 
> One more, and I do not know what to make of it. Meera, my assistant, she says there is a rumor going around that the moment you apply on the portal, you start getting phone calls. Salesmen, people turning up at your door, trying to sell you things. Now, how on earth would that happen?
> 
> And lastly, I keep hearing the new digital form is just not friendly. Some people say they are perfectly eligible, but simply cannot get through it. There are even fellows in the bazaar now who'll fill it out for you for a fee, because only they have figured out how it works. I would like to dismiss it as teething trouble—people always complain—but, who knows? We can always do better. Have a look at that, too.
> 
> Here, let me give you the rules so you have them. The pension is for residents 60 years of age and above on the date they apply, one application per person. The deadline for the department is 15 days, after which deemed approval kicks in, and an untouched file must actually be shown as approved to the citizen. And the application window closes at midnight, India Standard Time.
> 
> Come back to me once you have fixed what you can. Do not send me a report. Record me a short video, your face and your screen, and tell me the five things you fixed that matter most to these people, in order, and why. And, just as important, what you saw and chose to leave alone."

---

## Key Takeaways and Ground Reality Points

1. **Indic / Assamese Script Corruption & Truncation**:
   - Acknowledgement slips display `????` instead of Indic names (e.g. Assamese/Bengali/Devanagari).
   - Names are cut in half due to byte-level slicing (`[:20]` bytes instead of character-safe handling).
2. **Helpdesk Overwhelmed Due to Inability to Edit / Duplicate Blocker**:
   - Citizens making a minor typo have no way to edit or reapply.
   - Applications enforce a strict 1-application-per-mobile constraint, permanently locking out users with typos unless helpdesk manually deletes them.
3. **RTPS Act (Right to Public Services) Failure & Deemed Approval Halt**:
   - 15-day statutory SLA window.
   - Automatically approved overdue files until mid-March 2026 (Holi), then stopped completely due to script failure (`settings.ini` missing).
   - Backlog of pending applications violating state law.
4. **Month-end Performance Collapse**:
   - Severe site slowdown 2–3 days before disbursement deadline.
   - Tied to expensive PDF generation inside request threads, missing database indexes on large table (100k records), unoptimized queries.
5. **Data Leakage / Citizen Privacy Breach**:
   - Citizens receive unsolicited sales calls immediately after applying.
   - Publicly accessible SMS gateway (`/__gateway/`) and unauthenticated endpoints expose mobile numbers, application numbers, and citizen passwords.
   - Broken Object-Level Authorization (BOLA/IDOR) on `/application/<id>` and `/ack/<id>.pdf`.
6. **Hostile Digital Form / Intermediary Exploitation**:
   - Cryptic validation errors (e.g. `ERR_VAL_47` on file uploads > 100KB).
   - Forced irrelevant fields for widows (`husband_employer`).
   - Unfriendly date formats, creating a cottage industry of bazaar touts exploiting elderly citizens.
