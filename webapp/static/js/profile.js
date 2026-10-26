(function () {
  "use strict";

  var personalForm = document.getElementById("profile-personal-form");
  var saveButton = document.getElementById("profile-save-button");
  var passwordForm = document.getElementById("profile-password-form");
  var newPassword = document.getElementById("new-password");
  var confirmPassword = document.getElementById("confirm-password");
  var strength = document.getElementById("password-strength");
  var newPasswordError = document.getElementById("new-password-error");
  var confirmPasswordError = document.getElementById("confirm-password-error");
  var deleteDialog = document.getElementById("profile-delete-dialog");
  var openDeleteButton = document.getElementById("open-account-delete");
  var deleteForm = document.getElementById("profile-delete-form");
  var deleteConfirm = document.getElementById("profile-delete-confirm");
  var deleteCheckbox = deleteForm && deleteForm.querySelector('input[type="checkbox"]');
  var deletePassword = deleteForm && deleteForm.querySelector('input[name="password"]');
  var closeDeleteButtons = document.querySelectorAll("[data-profile-dialog-close]");
  var previousFocus = null;
  var initialPersonalValues = personalForm ? Array.from(new FormData(personalForm).entries()).map(function (entry) { return entry[1]; }).join("\u0000") : "";

  document.querySelectorAll(".profile-password-toggle").forEach(function (button) {
    button.addEventListener("click", function () {
      var input = button.parentElement && button.parentElement.querySelector("input");
      if (!input) return;
      var showing = input.type === "password";
      input.type = showing ? "text" : "password";
      button.textContent = showing ? "Hide" : "Show";
      button.setAttribute("aria-pressed", String(showing));
      button.setAttribute("aria-label", (showing ? "Hide " : "Show ") + (input.name || "password").replace(/_/g, " "));
    });
  });

  function currentPersonalValues() {
    return personalForm ? Array.from(new FormData(personalForm).entries()).map(function (entry) { return entry[1]; }).join("\u0000") : "";
  }

  if (personalForm && saveButton) {
    personalForm.addEventListener("input", function () {
      saveButton.disabled = currentPersonalValues() === initialPersonalValues;
    });
    personalForm.addEventListener("change", function () {
      saveButton.disabled = currentPersonalValues() === initialPersonalValues;
    });
  }

  function setInlineError(element, message) {
    if (!element) return;
    element.textContent = message;
    element.hidden = !message;
  }

  function updatePasswordStrength() {
    if (!newPassword || !strength) return;
    var value = newPassword.value;
    var score = 0;
    if (value.length >= 8) score += 1;
    if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score += 1;
    if (/\d/.test(value) || /[^A-Za-z0-9]/.test(value)) score += 1;
    var label = !value ? "—" : score <= 1 ? "Weak" : score === 2 ? "Fair" : "Strong";
    strength.className = "profile-strength" + (value ? " is-" + label.toLowerCase() : "");
    var strong = strength.querySelector("strong");
    if (strong) strong.textContent = label;
    setInlineError(newPasswordError, value && value.length < 8 ? "Use at least 8 characters." : "");
    if (confirmPassword && confirmPassword.value) {
      setInlineError(confirmPasswordError, confirmPassword.value !== value ? "Passwords do not match." : "");
    }
  }

  if (newPassword) newPassword.addEventListener("input", updatePasswordStrength);
  if (confirmPassword) {
    confirmPassword.addEventListener("input", function () {
      setInlineError(confirmPasswordError, confirmPassword.value && newPassword && confirmPassword.value !== newPassword.value ? "Passwords do not match." : "");
    });
  }

  if (passwordForm) {
    passwordForm.addEventListener("submit", function (event) {
      var tooShort = !newPassword || newPassword.value.length < 8;
      var mismatch = !confirmPassword || confirmPassword.value !== (newPassword && newPassword.value);
      setInlineError(newPasswordError, tooShort ? "Use at least 8 characters." : "");
      setInlineError(confirmPasswordError, mismatch ? "Passwords do not match." : "");
      if (tooShort || mismatch) {
        event.preventDefault();
        var invalidField = tooShort ? newPassword : confirmPassword;
        if (invalidField) invalidField.focus();
      }
    });
  }

  function updateDeleteButton() {
    if (deleteConfirm) deleteConfirm.disabled = !(deleteCheckbox && deleteCheckbox.checked && deletePassword && deletePassword.value.trim());
  }

  function closeDeleteDialog() {
    if (deleteDialog && deleteDialog.open) deleteDialog.close();
    if (previousFocus && typeof previousFocus.focus === "function") previousFocus.focus();
    previousFocus = null;
  }

  if (openDeleteButton && deleteDialog && typeof deleteDialog.showModal === "function") {
    openDeleteButton.addEventListener("click", function () {
      previousFocus = openDeleteButton;
      deleteDialog.showModal();
      if (deletePassword) deletePassword.focus();
    });
  }
  closeDeleteButtons.forEach(function (button) { button.addEventListener("click", closeDeleteDialog); });
  if (deleteCheckbox) deleteCheckbox.addEventListener("change", updateDeleteButton);
  if (deletePassword) deletePassword.addEventListener("input", updateDeleteButton);
  if (deleteDialog) {
    deleteDialog.addEventListener("click", function (event) {
      if (event.target === deleteDialog) closeDeleteDialog();
    });
    deleteDialog.addEventListener("cancel", function () { previousFocus = null; });
    deleteDialog.addEventListener("keydown", function (event) {
      if (event.key !== "Tab") return;
      var focusable = deleteDialog.querySelectorAll('button:not([disabled]), input:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])');
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
  updatePasswordStrength();
  updateDeleteButton();
})();
