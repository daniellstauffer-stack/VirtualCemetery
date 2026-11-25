# What families should be able to do

## One account, two spaces

**My Plan** is a private workspace for a living person. It holds their wishes, contacts, planning worksheet, and memories they are considering sharing. **The Memorial** is a separate page with a chosen name, portrait, life story, gallery, and guestbook. Its owner can preview it while alive. The default audience after publication is invited people. Public access and inclusion in the site's search each require an explicit choice.

Start with an English-language, invitation-only pilot for adults in one jurisdiction selected before launch. The operator will need a person available to review death reports, handle disputes, and respond to takedown requests. Broader availability depends on that capacity as well as on the technology.

## Who has permission

| Person | What they can do |
| --- | --- |
| Account owner | Edit their plan, decide the audience for each selected memory, designate or replace a steward, and export their information. Give a named person access to particular funeral instructions while alive or upon a verified death. See and revoke those grants. |
| Memorial steward | Accept or decline an invitation through a verified account. After a confirmed death, assemble the memorial within the owner's choices, moderate tributes, and invite viewers within the allowed audience. The app can call this role “the person who manages my memorial.” It grants no legal authority over the estate. |
| Funeral organizer | Receive the instructions and contact list the owner explicitly assigned to them. Confirm the actual event, recipients, and wording. The same person can hold both family roles if the owner chooses. |
| Relative or visitor | View a memorial within its audience, leave a flower or note according to the guestbook settings, report abuse, and remove their own contributions. |
| Site reviewer | Review a death report or dispute through a restricted staff screen. Record the reason for a decision. Access to case evidence is limited to assigned reviewers. Guestbook moderation alone grants no access to that evidence. |

## From a private plan to a memorial

1. **Prepare.** The owner selects memories, previews the memorial as a visitor, chooses who may see it, and invites a primary and optional backup steward. Invitations expire. Acceptance, replacement, and changes to the release instructions are recorded. Revoking a steward immediately ends their access.
2. **Report.** A steward submits a report and the minimum supporting evidence required by the launch policy. Support can receive a family report when a steward is unavailable. The report starts a private case. It never sends invitations or changes the public page. Inactivity cannot trigger a report.
3. **Verify.** A trained reviewer checks independent evidence, contacts the owner through an already verified channel, and gives them a documented opportunity to challenge the report. Silence alone is insufficient. Conflicting claims pause the case for a second reviewer. Keep evidence private and delete it on a defined schedule.
4. **Prepare the release.** After approval, the steward sees only material released to that role. They can arrange or omit selected memories and propose a family-written tribute with its own author credit. The owner’s audience is the ceiling. If nobody accepted the role, support follows the documented succession policy. The default is to keep unreleased material private.
5. **Publish and invite.** The steward previews and publishes the memorial. Publication, release of designated planning instructions, and sending funeral invitations are separate actions. An organizer can arrange a funeral promptly even if the family wants more time to prepare a memorial.
6. **Correct mistakes.** A living owner or family member can reach support without signing into the disputed account. Reviewers can suspend publication, stop queued invitations, revoke links, restore account access after identity checks, and record who received an erroneous notice so a correction can be sent. A delivered email or a downloaded photo cannot be recalled.

For a loved one who died without an account, add a later, separate family-created memorial flow. Verify the submitter's authority under the launch policy, label who created the page, check for duplicates, and accept competing claims. It gives a family no access to another person's private account or social accounts.

## Feature requirements and delivery order

| Release | Feature | What “working” means for a family |
| --- | --- | --- |
| Family pilot | Accounts and private planning | Sign in, recover access, save and revise burial or cremation preferences, service wishes, emergency contacts, and the location of important papers. Mark an item private or assign it to a named recipient. Show the last update. |
| Family pilot | Steward and verification | Invite, accept, replace, report, review, appeal, and reverse through the steps above. Staff can identify pending cases. The family gets a support contact and a plain explanation of timing. |
| Family pilot | Virtual grave and memories | Choose a portrait, dates, biography, and captioned photos. Use a private preview and then an invitation-only page with a stable address. Later add optional public discovery, audio stories with transcripts, and anniversary reminders people can turn off. |
| Family pilot | Flowers and guestbook | A signed-in guest can leave a free virtual flower or a note. Default to approval before notes appear. The steward can close the guestbook, hide a note, and act on reports. Visitors see which actions will display their names. |
| Family pilot | Funeral invitations | Maintain a private list by hand. An authorized organizer previews the date, time zone, location, wording, and recipients before sending. Use individual delivery, suppress duplicate sends, show delivery issues, and allow recipients to decline further messages. Keep location and livestream details within the event audience. |
| Family pilot | Portability and accessibility | Download a readable copy of the plan and an archive of owned memories. Offer keyboard navigation, labeled controls, legible text that enlarges, photo descriptions, and a printable view. Test with older adults and aim for WCAG 2.2 AA. |
| Family tools | Opt-in connections | Propose a labeled relationship between two memorials or profiles. Both owners or their authorized stewards must agree. Show the connection only to someone allowed to see both endpoints. Either side can withdraw. A relationship never grants access to a plan. |
| Family tools | Social and contact imports | Allow selected photos/stories from a user-supplied Facebook export and selected contacts from a CSV or vCard. Show a preview, detect duplicates, ask who owns the content, and let the user cancel before anything is saved. Consider connected-account imports after provider approval. |
| Family tools | Support the site | Offer an optional one-time contribution to the operator via hosted checkout. Disclose the payee, currency, refund contact, and how funds are used. Paying has no bearing on memorial access. Confirm the operator's tax status before making any deduction claim. |
| Planning and discovery | “Draft my wishes” wizard | Ask about jurisdiction, dependants, proposed guardians, categories of assets, intended gifts, executor preferences, and questions for counsel. Allow skip, resume, edit, and download of a private, dated worksheet. Avoid collecting account passwords or full financial identifiers. |
| Planning and discovery | Local professional directory | Search for funeral homes or estate-planning lawyers by town or postal code. Show specialty where verified, distance, rating, number and source of reviews, provider contact details, and a licensing lookup where available. Explain sorting and label paid placement. Unrated areas should still offer a licensing or professional directory link. |

**A legally usable draft will is a separate deliverable.** Choose a jurisdiction, engage qualified local estate counsel, and have them maintain the questions, templates, and eligibility rules. Route unsupported or complex cases to counsel. Label drafts clearly, identify the template version, and explain that jurisdiction’s signing and witnessing steps. Only add electronic execution or safekeeping after legal and security review. The first worksheet is useful to take to an appointment and conveys no promise that a will has been made.

## What to test before inviting a real family

| Try this | Release criterion |
| --- | --- |
| Publish one photograph alongside a private wish and a guest list. Try the page, search, export, and direct file addresses as a visitor. | Only the selected photograph is accessible to that visitor. Private names never appear in page previews or search results. |
| Remove the accepted steward, then try an old invitation and an existing signed-in session. | Both fail to open released information or take steward actions. |
| File a false report, dispute it, and rehearse reversing an approved case. | The pending report sends no funeral mail. Staff can unpublish, restore access, stop unsent jobs, and account for notices already delivered. |
| Agree to a relationship, then revoke consent or make one page private. | Viewers lose the relationship wherever they no longer have permission, including search and cached pages. |
| Import a contact twice, retry a send, and replay a payment notification. | One intended recipient, one confirmed delivery request for that invitation version, one recorded payment. Ambiguous delivery goes to reconciliation before any retry. |
| Use only a keyboard and a screen reader to add a memory and accept an invitation. | Both users can finish, understand the audience, and correct a mistake without assistance. |

Before the pilot, write the review, evidence retention, appeal, abuse, deletion, and service-closure policies for the selected jurisdiction. Tell families how to export their records, who can request removal of a photo, and how long support keeps reports and backups. Give the operator a tested recovery procedure and a way to contact families if it ever needs to close. A memorial's lasting value depends on those commitments.
