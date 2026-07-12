(() => {
  const toggle = document.getElementById("complication_occurred");
  const details = document.getElementById("complicationDetails");
  if (!toggle || !details) return;

  const sync = () => {
    details.classList.toggle("d-none", !toggle.checked);
  };
  toggle.addEventListener("change", sync);
  sync();
})();
