(function () {
  const count = document.getElementById("count");
  const asOf = document.getElementById("as-of");
  const tbody = document.getElementById("rows");

  function setCount(n) {
    if (count) count.textContent = n + (n === 1 ? " deal listed" : " deals listed");
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatDate(value) {
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
    return {
      name: name || "Untitled deal",
      summary: raw.summary || raw.headline || "",
      date: raw.date || raw.time || raw.announced || raw.announced_display || "",
      link: raw.link || raw.source_url || ""
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
      const summary = escapeHtml(deal.summary);
      const date = escapeHtml(formatDate(deal.date));
      const href = escapeHtml(deal.link);
      const nameCell = href
        ? "<a href=\"" + href + "\" target=\"_blank\" rel=\"noopener\">" + name + "</a>"
        : name;
      return (
        "<tr>" +
          "<td class=\"deal-name\">" + nameCell + "</td>" +
          "<td class=\"summary\">" + summary + "</td>" +
          "<td class=\"date\">" + date + "</td>" +
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
