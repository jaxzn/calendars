(function () {
  var input = document.querySelector("[data-search]");
  var cards = Array.prototype.slice.call(document.querySelectorAll("[data-team]"));
  var empty = document.querySelector("[data-empty]");

  function apply() {
    var q = (input && input.value || "").trim().toLowerCase();
    var shown = 0;
    cards.forEach(function (card) {
      var ok = !q || (card.getAttribute("data-team") || "").indexOf(q) !== -1;
      card.hidden = !ok;
      if (ok) shown += 1;
    });
    document.querySelectorAll("[data-division]").forEach(function (section) {
      section.hidden = !section.querySelector("[data-team]:not([hidden])");
    });
    document.querySelectorAll("[data-conference]").forEach(function (section) {
      section.hidden = !section.querySelector("[data-division]:not([hidden])");
    });
    if (empty) empty.hidden = shown !== 0;
  }

  if (input) input.addEventListener("input", apply);

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.left = "-9999px";
      document.body.appendChild(area);
      area.select();
      try {
        document.execCommand("copy") ? resolve() : reject(new Error("copy failed"));
      } catch (err) {
        reject(err);
      } finally {
        document.body.removeChild(area);
      }
    });
  }

  document.addEventListener("click", function (event) {
    var btn = event.target.closest("[data-copy]");
    if (!btn) return;
    var label = btn.getAttribute("data-label") || "Copy link";
    copyText(btn.getAttribute("data-copy") || "").then(function () {
      btn.textContent = "Copied";
    }, function () {
      btn.textContent = "Copy failed";
    }).then(function () {
      window.clearTimeout(btn._reset);
      btn._reset = window.setTimeout(function () { btn.textContent = label; }, 1600);
    });
  });
})();
