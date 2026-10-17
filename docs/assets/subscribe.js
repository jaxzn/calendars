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

  // iOS WKWebView browsers (Brave, Chrome, Edge, Firefox, in-app webviews)
  // treat a tapped webcal:// link as a main-frame navigation. Brave then
  // presents "Cannot Open Page" when the app returns from Calendar: its
  // navigation delegate shows that alert for a real linkActivated tap after
  // UIApplication.open succeeds. Chrome holds the policy decision until the
  // app is foregrounded again, so the unfinished webcal load is still pending
  // on resume. Safari follows the link itself and does not do this.
  //
  // Hand the URL to a throwaway iframe from the tap instead. The iframe
  // navigation is still user-initiated, so those browsers open Calendar, but
  // it is not a main-frame load and Brave classifies the scripted click as
  // synthetic, which is the case it already skips the alert for. The href
  // stays a plain webcal link for no-JS and for Safari, macOS, and desktop.
  var pageURL = location.href;
  var handoffArmed = false;
  var handoffBusy = false;

  function isIos() {
    var ua = navigator.userAgent || "";
    if (/iPad|iPhone|iPod/i.test(ua)) return true;
    return navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
  }

  function needsWebcalHandoff() {
    if (!isIos()) return false;
    var ua = navigator.userAgent || "";
    if (/CriOS|FxiOS|EdgiOS|OPiOS|OPT\/|DuckDuckGo|Brave|GSA\/|FBAN|FBAV|Instagram|Line\//i.test(ua)) return true;
    if (typeof navigator.brave !== "undefined") return true;
    if (/Version\/[\d.]+/i.test(ua) && /Safari/i.test(ua)) {
      try {
        var handlers = window.webkit && window.webkit.messageHandlers;
        return !!(handlers && Object.keys(handlers).length);
      } catch (err) {
        return false;
      }
    }
    return /AppleWebKit/i.test(ua);
  }

  function settleHandoff() {
    if (!handoffArmed) return;
    handoffArmed = false;
    try {
      if (location.protocol !== "http:" && location.protocol !== "https:") {
        location.replace(pageURL);
        return;
      }
    } catch (err) {}
    // Re-pin this history entry, then drop a provisional main-frame load if
    // the browser started one anyway and retries it on foreground.
    try { history.replaceState(history.state, document.title, location.href); } catch (err) {}
    try { window.stop(); } catch (err) {}
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") settleHandoff();
  });
  window.addEventListener("pageshow", settleHandoff);

  function openWebcal(url) {
    var iframe = document.createElement("iframe");
    iframe.name = "webcal-handoff";
    iframe.setAttribute("aria-hidden", "true");
    iframe.tabIndex = -1;
    // display:none and the hidden attribute make WebKit skip the frame.
    iframe.style.cssText = "position:fixed;left:-10000px;top:0;width:1px;height:1px;border:0;opacity:0;pointer-events:none";
    iframe.src = "about:blank";
    document.body.appendChild(iframe);

    var opened = false;
    try {
      var doc = iframe.contentDocument;
      if (doc) {
        if (!doc.body) {
          doc.open();
          doc.write("<!doctype html><title></title><body></body>");
          doc.close();
        }
        var anchor = doc.createElement("a");
        anchor.href = url;
        anchor.target = "_self";
        anchor.tabIndex = -1;
        doc.body.appendChild(anchor);
        anchor.click();
        opened = true;
        try {
          if (doc.activeElement && doc.activeElement.blur) doc.activeElement.blur();
        } catch (err) {}
      }
    } catch (err) {
      opened = false;
    }
    if (!opened) {
      try { iframe.src = url; } catch (err2) {}
    }
    try {
      if (document.activeElement && document.activeElement !== document.body && document.activeElement.blur) {
        document.activeElement.blur();
      }
    } catch (err) {}

    function removeFrame() {
      if (iframe.parentNode) iframe.parentNode.removeChild(iframe);
    }
    window.addEventListener("pagehide", removeFrame, { once: true });
    window.setTimeout(removeFrame, 4000);
  }

  document.addEventListener("click", function (event) {
    var el = event.target;
    if (!el || !el.closest) return;
    var link = el.closest("a");
    if (!link || (link.protocol || "").toLowerCase() !== "webcal:") return;
    if (event.defaultPrevented) return;
    if (typeof event.button === "number" && event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (!needsWebcalHandoff()) return;
    if (handoffBusy) {
      event.preventDefault();
      return;
    }
    var url = link.href;
    if (!url || url.toLowerCase().indexOf("webcal:") !== 0) return;

    event.preventDefault();
    handoffBusy = true;
    handoffArmed = true;
    window.setTimeout(function () { handoffBusy = false; }, 1500);
    try { history.replaceState(history.state, document.title, location.href); } catch (err) {}
    openWebcal(url);
  });
})();
