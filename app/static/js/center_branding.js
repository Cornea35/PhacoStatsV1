(() => {
  const select = document.getElementById("center_code");
  if (!select) return;
  const shortEl = document.getElementById("centerShortName");
  const fullEl = document.getElementById("centerFullName");
  const styleEl = document.getElementById("brandTheme");
  const apply = async () => {
    const code = select.value;
    if (!code) return;
    try {
      const res = await fetch(`/api/centers/${encodeURIComponent(code)}/branding`);
      if (!res.ok) return;
      const data = await res.json();
      if (styleEl && data.css) styleEl.textContent = `:root { ${data.css} }`;
      if (shortEl) shortEl.textContent = data.short_name || "";
      if (fullEl) fullEl.textContent = data.full_name || "";
      const ph = document.querySelector(".brand-placeholder");
      if (ph && data.placeholder) ph.textContent = data.placeholder;
      document.querySelectorAll(".brand-org-login").forEach((el) => {
        if (el.id !== "centerShortName") el.textContent = data.short_name || el.textContent;
      });
    } catch (_) {
      /* ignore network errors on branding preview */
    }
  };
  select.addEventListener("change", apply);
  apply();
})();
