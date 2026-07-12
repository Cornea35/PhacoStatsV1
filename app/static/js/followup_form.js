(() => {
  const surgeryDate = window.PHACO_SURGERY_DATE;
  const sphereEl = document.getElementById("sphere");
  const cylinderEl = document.getElementById("cylinder");
  const axisEl = document.getElementById("axis");
  const visitDateEl = document.getElementById("visit_date");
  const postopEl = document.getElementById("postopDaysPreview");
  if (!sphereEl || !cylinderEl) return;

  function setText(field, value) {
    const el = document.querySelector(`[data-field="${field}"]`);
    if (el) el.textContent = value;
  }

  function updatePostopDays() {
    if (!visitDateEl || !visitDateEl.value || !surgeryDate) {
      if (postopEl) postopEl.value = "—";
      return;
    }
    const a = new Date(surgeryDate + "T00:00:00");
    const b = new Date(visitDateEl.value + "T00:00:00");
    const days = Math.round((b - a) / 86400000);
    postopEl.value = Number.isFinite(days) ? String(days) : "—";
  }

  async function refreshPreview() {
    const sphere = parseFloat(sphereEl.value);
    let cylinder = parseFloat(cylinderEl.value);
    if (!Number.isFinite(sphere) || !Number.isFinite(cylinder)) return;
    if (cylinder > 0) {
      setText("orient", "Cilindro debe ser ≤ 0");
      setText("seq", "—");
      return;
    }
    let axis = axisEl.value === "" ? null : parseFloat(axisEl.value);
    if (Math.abs(cylinder) < 1e-9) {
      axis = null;
      axisEl.disabled = true;
    } else {
      axisEl.disabled = false;
    }
    const params = new URLSearchParams({
      sphere: String(sphere),
      cylinder: String(cylinder),
    });
    if (axis !== null && Number.isFinite(axis)) params.set("axis", String(axis));
    try {
      const res = await fetch(`/surgeries/api/refraction-preview?${params.toString()}`);
      const data = await res.json();
      if (!res.ok) {
        setText("seq", "—");
        setText("cyl", "—");
        setText("orient", data.error || "Error");
        return;
      }
      setText("seq", data.spherical_equivalent.toFixed(2));
      setText("cyl", data.residual_astigmatism.toFixed(2));
      setText("cylSigned", Number(data.cylinder).toFixed(2));
      setText("orient", data.orientation_label);
      setText("j0", Number(data.j0).toFixed(3));
      setText("j45", Number(data.j45).toFixed(3));
      setText("seqStars", data.spherical_equivalent_stars + "★");
      setText("astigStars", data.astigmatism_stars + "★");
      setText("overallStars", Number(data.overall_refractive_stars).toFixed(1) + "★");
    } catch (_) {
      /* preview optional */
    }
  }

  [sphereEl, cylinderEl, axisEl].forEach((el) => {
    el.addEventListener("input", refreshPreview);
    el.addEventListener("change", refreshPreview);
  });
  if (visitDateEl) {
    visitDateEl.addEventListener("change", updatePostopDays);
    visitDateEl.addEventListener("input", updatePostopDays);
  }
  updatePostopDays();
  refreshPreview();
})();
