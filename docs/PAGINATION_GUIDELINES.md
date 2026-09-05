# SSK ERP Standard Pagination Guidelines

## Overview
All tables, data lists, and high-density tabular views across SSK ERP must utilize the standardized pagination system. This ensures a uniform, premium brand aesthetic, consistent user navigation, and maximum code reuse across existing and future feature additions.

---

## Core Components & Hooks

The pagination system is exported directly from `../components/ui-kit`:

```javascript
import { PaginationControls, usePagination } from "../components/ui-kit";
```

Alternatively, direct imports are available:
- Component: `import PaginationControls from "@/components/PaginationControls";`
- Hook: `import { usePagination } from "@/hooks/usePagination";`
- Virtualized Table: `<ResponsiveTable pagination={paginationProps} />`

---

## 1. Client-Side Slicing Pattern (Default)

For pages that load an array of records into memory:

```javascript
import { useState } from "react";
import { Card, PaginationControls, usePagination } from "../components/ui-kit";

export default function MyFeatureList() {
  const [items, setItems] = useState([]);

  // Setup standardized pagination (default 25 items per page)
  const {
    paginatedItems,
    paginationProps,
    resetPage,
  } = usePagination(items, {
    initialPageSize: 25,
    pageSizeOptions: [10, 25, 50, 100],
    testIdPrefix: "my-feature-pagination",
  });

  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            {/* Table headers */}
          </thead>
          <tbody>
            {paginatedItems.map((item) => (
              <tr key={item.id}>
                {/* Table cells */}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Standard ERP Pagination Footer */}
      <div className="px-5 py-3 bg-white border-t border-slate-200">
        <PaginationControls {...paginationProps} />
      </div>
    </Card>
  );
}
```

---

## 2. Server-Side / API Pagination Pattern

For endpoints that accept `page` and `limit` (or `page_size`) query parameters:

```javascript
import { useState, useEffect } from "react";
import { PaginationControls, usePagination } from "../components/ui-kit";
import { http } from "../lib/api";

export default function ServerSideList() {
  const [data, setData] = useState([]);
  const [totalCount, setTotalCount] = useState(0);

  const {
    page,
    pageSize,
    paginationProps,
  } = usePagination(totalCount, {
    initialPageSize: 25,
    pageSizeOptions: [10, 25, 50, 100],
    testIdPrefix: "server-pagination",
  });

  useEffect(() => {
    http.get(`/my-endpoint?page=${page}&limit=${pageSize}`)
      .then((res) => {
        setData(res.data.items);
        setTotalCount(res.data.total);
      });
  }, [page, pageSize]);

  return (
    <div>
      {/* Render data rows */}
      <PaginationControls {...paginationProps} />
    </div>
  );
}
```

---

## 3. ResponsiveTable Integration Pattern

When using the ERP's `ResponsiveTable` component (which automatically provides desktop virtualized tables and mobile card layouts), simply pass the `pagination` prop:

```javascript
import ResponsiveTable from "../components/ResponsiveTable";
import { usePagination } from "../components/ui-kit";

export default function OrderPipeline() {
  const { paginatedItems, paginationProps } = usePagination(orders, {
    initialPageSize: 25,
    testIdPrefix: "orders-pipeline-pagination",
  });

  return (
    <ResponsiveTable
      columns={columns}
      rows={paginatedItems}
      rowKey={(r) => r.id}
      pagination={paginationProps}
    />
  );
}
```

---

## UI Specification & Defaults

- **Default Page Size**: `25` records per page.
- **Page Size Options**: `[10, 25, 50, 100]`.
- **Primary Action Color**: Active page buttons use brand navy `#1E3A8A` with white text and font-mono typography.
- **Record Counter**: Displays `Showing <start> to <end> of <total> records` (or compact format `1–25 of 142` when `rangeTextFormat="compact"` is set).
- **Navigation Controls**: First (`«`), Previous (`‹`), sliding 5-page numeric pills, Next (`›`), and Last (`»`) buttons with boundary auto-disabling.
- **Test ID Convention**: Always specify a descriptive `testIdPrefix` (e.g. `testIdPrefix="my-feature-pagination"`), which automatically produces:
  - `<prefix>-bar` (container)
  - `<prefix>-count-info` (record range text)
  - `<prefix>-size-select` (per-page select)
  - `<prefix>-first`, `<prefix>-prev`, `<prefix>-page-<N>`, `<prefix>-next`, `<prefix>-last`
