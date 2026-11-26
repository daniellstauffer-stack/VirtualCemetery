/* Virtual Cemetery — Accessible Progressive Enhancement */
(function () {
  "use strict";

  // Copy private invite link helper with polite ARIA announcement
  document.addEventListener("click", function (event) {
    const copyBtn = event.target.closest("[data-copy-text]");
    if (!copyBtn) return;
    const text = copyBtn.getAttribute("data-copy-text");
    if (!text || !navigator.clipboard) return;
    navigator.clipboard.writeText(text).then(function () {
      const original = copyBtn.textContent;
      copyBtn.textContent = "Link copied";
      setTimeout(function () {
        copyBtn.textContent = original;
      }, 2200);
    });
  });

  // Live audience plain-language helper on Add/Edit Memory form
  const audienceHelpMap = {
    private_only: "Only you can see this. Even after death, it stays private and is never released to your steward or visitors.",
    steward_after_death: "Only you can see this today. After a verified death, your steward may read it privately, but it will not be published on the memorial.",
    invited_memorial: "Only you can see this today (and in your preview). After a verified death, your steward may place it on your memorial for invited family.",
    public_memorial: "Only you can see this today (and in your preview). After a verified death, your steward may publish it within your memorial's audience ceiling."
  };

  const audienceHint = document.getElementById("audience-live-summary");
  if (audienceHint) {
    document.querySelectorAll('input[name="audience"]').forEach(function (radio) {
      radio.addEventListener("change", function () {
        if (audienceHelpMap[this.value]) {
          audienceHint.textContent = audienceHelpMap[this.value];
        }
      });
    });
  }
})();
