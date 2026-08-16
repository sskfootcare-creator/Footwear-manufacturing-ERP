// scratch/test_archive_clustering.mjs

function sortSizes(a, b) {
  const na = parseFloat(a), nb = parseFloat(b);
  if (!isNaN(na) && !isNaN(nb)) return na - nb;
  return String(a).localeCompare(String(b));
}

function groupJobsByColor(jobs) {
  const groups = {};
  for (const j of jobs) {
    const color = j.color || "—";
    const key = `${j.po_number}::${j.style_code}::${color}`;
    if (!groups[key]) {
      groups[key] = {
        key, po_number: j.po_number, po_id: j.po_id, style_id: j.style_id, style_code: j.style_code,
        client_name: j.client_name, description: j.description, delivery_date: j.delivery_date,
        color, rows: [], sizes: new Set(),
      };
    }
    groups[key].rows.push(j);
    groups[key].sizes.add(String(j.size || "—"));
  }
  return Object.values(groups).map(g => ({
    ...g,
    sizes: Array.from(g.sizes).sort(sortSizes),
    totalQty: g.rows.reduce((s, r) => s + (r.quantity || 0), 0),
  }));
}

export function clusterArchivedGroups(groups, dispatchRecordByJobId = {}, invoices = []) {
  if (!groups || !groups.length) return [];

  // Map job_id -> invoice (specifically accounts for merged: true invoices)
  const invoiceByJobId = {};
  for (const inv of invoices || []) {
    if (inv && Array.isArray(inv.job_ids)) {
      for (const jid of inv.job_ids) {
        if (jid) invoiceByJobId[String(jid)] = inv;
      }
    }
  }

  const clustersMap = new Map();

  for (const g of groups) {
    let resolvedInvoiceId = null;
    let resolvedInvoiceNo = null;
    let isMerged = false;
    let matchedInvoice = null;
    let matchedDr = null;

    for (const row of g.rows || []) {
      const inv = invoiceByJobId[String(row.id)];
      if (inv) {
        resolvedInvoiceId = inv.id || String(inv._id);
        resolvedInvoiceNo = inv.invoice_no;
        isMerged = Boolean(inv.merged);
        matchedInvoice = inv;
        break;
      }

      const dr = dispatchRecordByJobId[row.id];
      if (dr) {
        resolvedInvoiceId = dr.invoice_id || dr.id;
        resolvedInvoiceNo = dr.invoice_no;
        matchedDr = dr;
        break;
      }
    }

    const clusterKey = resolvedInvoiceId ? `inv:${resolvedInvoiceId}` : `group:${g.key}`;

    if (!clustersMap.has(clusterKey)) {
      clustersMap.set(clusterKey, {
        id: clusterKey,
        invoice_id: resolvedInvoiceId,
        invoice_no: resolvedInvoiceNo,
        is_merged: isMerged,
        invoice: matchedInvoice,
        dispatch_record: matchedDr,
        groups: [g],
      });
    } else {
      const cluster = clustersMap.get(clusterKey);
      cluster.groups.push(g);
      cluster.is_merged = true; // Multiple groups share this invoice
      if (matchedInvoice && !cluster.invoice) cluster.invoice = matchedInvoice;
      if (matchedDr && !cluster.dispatch_record) cluster.dispatch_record = matchedDr;
    }
  }

  return Array.from(clustersMap.values());
}

// ──────────────────────────── TEST EXECUTION ────────────────────────────

console.log("=== STEP 1: Setting up mock archived jobs ===");
const mockArchivedJobs = [
  // Group A (PO-100, STYLE-1, Black) - 2 rows
  { id: "job-1a", po_number: "PO-100", po_id: "po-1", style_code: "STYLE-1", color: "Black", size: "8", quantity: 15, client_name: "Client X" },
  { id: "job-1b", po_number: "PO-100", po_id: "po-1", style_code: "STYLE-1", color: "Black", size: "9", quantity: 15, client_name: "Client X" },

  // Group B (PO-100, STYLE-1, Brown) - 1 row
  { id: "job-2a", po_number: "PO-100", po_id: "po-1", style_code: "STYLE-1", color: "Brown", size: "8", quantity: 20, client_name: "Client X" },

  // Group C (PO-101, STYLE-2, Navy) - 1 row (Individual dispatch/invoice)
  { id: "job-3a", po_number: "PO-101", po_id: "po-2", style_code: "STYLE-2", color: "Navy", size: "10", quantity: 50, client_name: "Client Y" },

  // Group D (PO-102, STYLE-3, Grey) - 1 row (No invoice generated yet)
  { id: "job-4a", po_number: "PO-102", po_id: "po-3", style_code: "STYLE-3", color: "Grey", size: "7", quantity: 10, client_name: "Client Z" },
];

console.log("=== STEP 2: Running groupJobsByColor ===");
const initialGroups = groupJobsByColor(mockArchivedJobs);
console.log(`initialGroups count: ${initialGroups.length}`);
initialGroups.forEach((g, i) => {
  console.log(`  Group ${i+1}: key="${g.key}", PO=${g.po_number}, Style=${g.style_code}, Color=${g.color}, Qty=${g.totalQty}`);
});

console.log("\n=== STEP 3: Setting up mock Invoices and Dispatch Records ===");
const mockInvoices = [
  {
    id: "inv-merged-001",
    invoice_no: "SSK26-27-020",
    merged: true,
    po_numbers: ["PO-100"],
    job_ids: ["job-1a", "job-1b", "job-2a"], // Group A + Group B
    client_name: "Client X",
  },
  {
    id: "inv-single-002",
    invoice_no: "SSK26-27-021",
    merged: false,
    po_numbers: ["PO-101"],
    job_ids: ["job-3a"], // Group C only
    client_name: "Client Y",
  },
];

const mockDispatchRecordByJobId = {
  "job-1a": { id: "dr-1", invoice_id: "inv-merged-001", invoice_no: "SSK26-27-020" },
  "job-1b": { id: "dr-1", invoice_id: "inv-merged-001", invoice_no: "SSK26-27-020" },
  "job-2a": { id: "dr-2", invoice_id: "inv-merged-001", invoice_no: "SSK26-27-020" },
  "job-3a": { id: "dr-3", invoice_id: "inv-single-002", invoice_no: "SSK26-27-021" },
};

console.log("\n=== STEP 4: Running clusterArchivedGroups (Second Pass) ===");
const clusters = clusterArchivedGroups(initialGroups, mockDispatchRecordByJobId, mockInvoices);
console.log(`Derived clusters count: ${clusters.length}`);

clusters.forEach((c, i) => {
  console.log(`\nCluster ${i+1}:`);
  console.log(`  ID: ${c.id}`);
  console.log(`  Invoice No: ${c.invoice_no}`);
  console.log(`  Is Merged: ${c.is_merged}`);
  console.log(`  Contained Groups Count: ${c.groups.length}`);
  c.groups.forEach(g => {
    console.log(`    - Group: key="${g.key}", PO=${g.po_number}, Color=${g.color}, Qty=${g.totalQty}`);
  });
});

console.log("\n=== STEP 5: Assertions & Verification ===");

// 1. Total clusters should be 3 (1 merged cluster containing 2 groups + 2 single-item clusters)
if (clusters.length !== 3) {
  throw new Error(`Expected 3 clusters, got ${clusters.length}`);
}

// 2. Cluster 1 should contain exactly Group A and Group B
const mergedCluster = clusters.find(c => c.invoice_id === "inv-merged-001");
if (!mergedCluster) throw new Error("Merged cluster not found!");
if (!mergedCluster.is_merged) throw new Error("Merged cluster should have is_merged === true!");
if (mergedCluster.groups.length !== 2) throw new Error(`Merged cluster should contain 2 groups, got ${mergedCluster.groups.length}`);
const mergedGroupColors = mergedCluster.groups.map(g => g.color).sort();
if (JSON.stringify(mergedGroupColors) !== JSON.stringify(["Black", "Brown"])) {
  throw new Error(`Expected merged groups ['Black', 'Brown'], got ${JSON.stringify(mergedGroupColors)}`);
}
console.log("ASSERTION 1 PASSED: Merged groups (Group A and Group B) are grouped together into one cluster!");

// 3. Cluster 2 should contain single Group C
const singleCluster = clusters.find(c => c.invoice_id === "inv-single-002");
if (!singleCluster) throw new Error("Single invoice cluster not found!");
if (singleCluster.is_merged) throw new Error("Single invoice cluster should NOT be marked merged!");
if (singleCluster.groups.length !== 1) throw new Error(`Single cluster should contain 1 group, got ${singleCluster.groups.length}`);
if (singleCluster.groups[0].color !== "Navy") throw new Error("Single cluster group should be Navy");
console.log("ASSERTION 2 PASSED: Individual invoice group (Group C) remains a single-item cluster!");

// 4. Cluster 3 should contain standalone Group D (no invoice)
const noInvCluster = clusters.find(c => c.id === "group:PO-102::STYLE-3::Grey");
if (!noInvCluster) throw new Error("No-invoice cluster not found!");
if (noInvCluster.is_merged) throw new Error("No-invoice cluster should NOT be marked merged!");
if (noInvCluster.groups.length !== 1) throw new Error(`No-invoice cluster should contain 1 group, got ${noInvCluster.groups.length}`);
if (noInvCluster.groups[0].color !== "Grey") throw new Error("No-invoice cluster group should be Grey");
console.log("ASSERTION 3 PASSED: Standalone group with no invoice remains a single-item cluster!");

console.log("\nALL ARCHIVE CLUSTERING TESTS PASSED PERFECTLY!");
