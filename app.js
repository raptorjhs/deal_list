(function () {
  const count = document.getElementById("count");
  const asOf = document.getElementById("as-of");
  const tbody = document.getElementById("rows");
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatDate(value) {
    if (!value) return "";
    if (/^\d{1,2} [A-Z][a-z]{2} \d{4}$/.test(String(value).trim())) return String(value).trim();
    var d = new Date(value);
    if (isNaN(d.getTime())) return String(value);
    return d.getUTCDate() + " " + months[d.getUTCMonth()] + " " + d.getUTCFullYear();
  }

  function googleNewsUrl(name) {
    return "https://news.google.com/search?q=" + encodeURIComponent(name) + "&hl=en-US&gl=US&ceid=US:en";
  }

  function normalizeDeal(raw) {
    var name = raw.name;
    if (!name && (raw.company_a || raw.company_b)) {
      name = [raw.company_a, raw.company_b].filter(Boolean).join(" / ");
    }
    name = name || "Untitled deal";
    return {
      name: name,
      summary: raw.summary || raw.headline || "",
      date: formatDate(raw.date || raw.time || raw.announced || raw.updated || ""),
      link: googleNewsUrl(name)
    };
  }

  function listDeals(data) {
    if (Array.isArray(data)) return data.map(normalizeDeal);
    if (data && Array.isArray(data.deals)) return data.deals.map(normalizeDeal);
    return [];
  }

  function render(data) {
    var deals = listDeals(data);
    if (asOf && data && data.updated) asOf.textContent = "As of " + formatDate(data.updated);
    tbody.innerHTML = deals.map(function (deal) {
      var name = escapeHtml(deal.name);
      var href = escapeHtml(deal.link);
      return (
        "<tr>" +
          "<td class=\"deal-name\"><a href=\"" + href + "\" target=\"_blank\" rel=\"noopener\">" + name + "</a></td>" +
          "<td class=\"summary\">" + escapeHtml(deal.summary) + "</td>" +
          "<td class=\"date\">" + escapeHtml(deal.date) + "</td>" +
        "</tr>"
      );
    }).join("");
    if (count) count.textContent = deals.length + (deals.length === 1 ? " deal listed" : " deals listed");
  }

  fetch("deals.json", { cache: "no-store" })
    .then(function (res) {
      if (!res.ok) throw new Error("Could not load deals.json");
      return res.json();
    })
    .then(render)
    .catch(function (err) {
      if (count) count.textContent = "Could not load deals.json";
      console.error(err);
    });
})();
