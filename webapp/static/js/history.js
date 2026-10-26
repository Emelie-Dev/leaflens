(function () {
  "use strict";

  var dialog = document.getElementById("history-delete-dialog");
  var deleteForm = document.getElementById("history-delete-form");
  var triggers = document.querySelectorAll(".history-delete-trigger");
  var closeButtons = document.querySelectorAll("[data-dialog-close]");
  var previousFocus = null;

  function closeDialog() {
    if (dialog && dialog.open) dialog.close();
    if (previousFocus && typeof previousFocus.focus === "function") previousFocus.focus();
    previousFocus = null;
  }

  function openDialog(trigger) {
    if (!dialog || !deleteForm || typeof dialog.showModal !== "function") return;
    var action = trigger.getAttribute("data-delete-url");
    if (!action) return;
    deleteForm.action = action;
    previousFocus = trigger;
    dialog.showModal();
    var cancel = dialog.querySelector("[data-dialog-close]");
    if (cancel) cancel.focus();
  }

  triggers.forEach(function (trigger) {
    trigger.addEventListener("click", function (event) {
      event.stopPropagation();
      openDialog(trigger);
    });
  });

  closeButtons.forEach(function (button) {
    button.addEventListener("click", closeDialog);
  });

  if (dialog) {
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) closeDialog();
    });
    dialog.addEventListener("cancel", function () {
      previousFocus = null;
    });
    dialog.addEventListener("keydown", function (event) {
      if (event.key !== "Tab") return;
      var focusable = dialog.querySelectorAll('button:not([disabled]), input:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])');
      if (!focusable.length) {
        event.preventDefault();
        return;
      }
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
  }

  document.querySelectorAll(".history-row-link[data-href]").forEach(function (row) {
    row.addEventListener("click", function (event) {
      if (event.target.closest("a, button, form")) return;
      window.location.href = row.getAttribute("data-href");
    });
    row.addEventListener("keydown", function (event) {
      if (event.key !== "Enter" && event.key !== " ") return;
      if (event.target !== row) return;
      event.preventDefault();
      window.location.href = row.getAttribute("data-href");
    });
  });
})();
