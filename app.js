(function () {
  const count = document.getElementById("count");
  const asOf = document.getElementById("as-of");
  const tbody = document.getElementById("rows");

  function setCount(n) {
    if (count) count.textContent = n + (n === 1 ? " deal listed" : " deals listed");
  }

  function statusClass(status) {
    if (status === "closed" || status === "completed") return "closed";
    if (status === "review" || status === "litigation") return "review";
    return "pending";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatTime(value) {
    if (!value) return "";
    var d = new Date(value);
    if (isNaN(d.getTime())) return String(value);
    var months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    return d.getUTCDate() + " " + months[d.getUTCMonth()] + " " + d.getUTCFullYear();
  }

  function normalizeDeal(raw) {
    var name = raw.name;
    if (!name && (raw.company_a || raw.company_b)) {
      name = [raw.company_a, raw.company_b].filter(Boolean).join(" / ");
    }
    var announced = raw.announced || (raw.time ? String(raw.time).slice(0, 10) : "");
    return {
      name: name || raw.headline || "Untitled deal",
      status: raw.status || "pending",
      status_label: raw.status_label || "Pending",
      announced_display: raw.announced_display || formatTime(raw.time || announced),
      headline: raw.headline || "",
      source_url: raw.source_url || raw.link || ""
    };
  }

  function listDeals(data) {
    if (Array.isArray(data)) return data.map(normalizeDeal);
    if (data && Array.isArray(data.deals)) return data.deals.map(normalizeDeal);
    return [];
  }

  function render(data) {
    const deals = listDeals(data);
    if (asOf && data && data.updated) asOf.textContent = "As of " + data.updated;
    tbody.innerHTML = deals.map((deal) => {
      const name = escapeHtml(deal.name);
      const status = escapeHtml(deal.status);
      const label = escapeHtml(deal.status_label);
      const date = escapeHtml(deal.announced_display || "");
      const headline = escapeHtml(deal.headline);
      const href = escapeHtml(deal.source_url);
      const nameCell = href
        ? "<a href=\"" + href + "\" target=\"_blank\" rel=\"noopener\">" + name + "</a>"
        : name;
      return (
        "<tr>" +
          "<td class=\"deal-name\">" + nameCell + "</td>" +
          "<td><span class=\"status " + statusClass(status) + "\">" + label + "</span></td>" +
          "<td class=\"date\">" + date + "</td>" +
          "<td class=\"summary\">" + headline + "</td>" +
        "</tr>"
      );
    }).join("");
    setCount(deals.length);
  }

  fetch("deals.json", { cache: "no-store" })
    .then((res) => {
      if (!res.ok) throw new Error("Could not load deals.json");
      return res.json();
    })
    .then(render)
    .catch((err) => {
      if (count) count.textContent = "Could not load deals.json";
      console.error(err);
    });
})();
