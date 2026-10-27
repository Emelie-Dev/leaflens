(function () {
  "use strict";

  var dialog = document.getElementById("admin-delete-dialog");
  var deleteForm = document.getElementById("admin-delete-form");
  var message = document.querySelector("[data-confirm-message]");
  var deleteButtons = document.querySelectorAll("[data-confirm-delete]");
  var closeButtons = document.querySelectorAll("[data-dialog-close]");
  var previousFocus = null;

  function closeDialog() {
    if (dialog && dialog.open) {
      dialog.close();
    }
    if (previousFocus && typeof previousFocus.focus === "function") {
      previousFocus.focus();
    }
    previousFocus = null;
  }

  function openDialog(button) {
    if (!dialog || !deleteForm || !message || typeof dialog.showModal !== "function") {
      return;
    }

    var action = button.getAttribute("data-action");
    if (!action) {
      return;
    }

    deleteForm.setAttribute("action", action);
    previousFocus = button;
    var text = button.getAttribute("data-message") || "Are you sure you want to delete this item?";
    message.textContent = text;
    dialog.showModal();
    var cancelButton = dialog.querySelector("[data-dialog-close]");
    if (cancelButton) {
      cancelButton.focus();
    }
  }

  deleteButtons.forEach(function (button) {
    button.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      openDialog(button);
    });
  });

  closeButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      closeDialog();
    });
  });

  if (dialog) {
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) {
        closeDialog();
      }
    });

    dialog.addEventListener("cancel", function () {
      closeDialog();
    });
  }
})();
