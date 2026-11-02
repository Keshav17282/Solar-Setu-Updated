(function () {
  "use strict";

  const form = document.getElementById("subsidy-calculator-form");
  if (!form) return;

  const capacityInput = document.getElementById("subsidy-capacity");
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
  const rupee = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

  document.querySelectorAll("[data-capacity]").forEach((button) => {
    button.addEventListener("click", () => {
      capacityInput.value = button.dataset.capacity;
      document.querySelectorAll("[data-capacity]").forEach((item) => item.classList.toggle("active", item === button));
    });
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const error = document.getElementById("result-error");
    error.hidden = true;

    const payload = {
      state: document.getElementById("subsidy-state").value,
      capacity: capacityInput.value,
      category: document.getElementById("subsidy-category").value,
      configuration: document.getElementById("subsidy-configuration").value,
      csrf_token: csrfToken,
    };

    try {
      const response = await fetch("/api/subsidy/calculate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || "Unable to calculate subsidy.");

      const result = data.result;
      document.getElementById("central-result").textContent = rupee.format(result.central_subsidy);
      document.getElementById("state-result").textContent = rupee.format(result.state_additional_subsidy);
      document.getElementById("combined-result").textContent = rupee.format(result.indicative_combined_subsidy);
      document.getElementById("final-result").textContent = rupee.format(result.final_estimated_subsidy);
      document.getElementById("result-status").textContent = result.eligibility_status;
      document.getElementById("result-explanation").textContent = result.explanation;
      document.getElementById("result-warning").textContent = result.warning;
      document.getElementById("result-warning").hidden = !result.warning;
      document.querySelector(".subsidy-result").classList.toggle("not-eligible", !result.eligible);
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    }
  });
})();
