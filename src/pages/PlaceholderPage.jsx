import { products } from "../data/mockData.js";
import { pageMeta } from "../routes/routes.js";
import {
  Button,
  Card,
  EmptyState,
  Input,
  SelectPlaceholder,
  StatusBadge,
  Table,
} from "../components/ui/index.js";

function ProductPreviewTable() {
  return (
    <Table columns={["Ürün", "Marka", "Kategori", "Durum", "Aksiyon"]}>
      {products.slice(0, 5).map((product) => (
        <tr key={product.name}>
          <td>
            <strong>{product.name}</strong>
            <small>{product.price}</small>
          </td>
          <td>{product.brand}</td>
          <td>{product.category}</td>
          <td>
            <StatusBadge status="Onaylandı" />
          </td>
          <td>
            <a className="table-action" href="#/products">
              Düzenle
            </a>
          </td>
        </tr>
      ))}
    </Table>
  );
}

export function PlaceholderPage({ path }) {
  const meta = pageMeta[path] || pageMeta["/campaigns"];

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>{meta.title}</h2>
          <p>{meta.description}</p>
        </div>
        <div className="page-actions">
          <Button variant="primary" href={meta.actionHref}>
            {meta.action}
          </Button>
        </div>
      </section>
      <section className="placeholder-grid">
        <Card title="Filtreler" className="span-12">
          <div className="form-grid">
            <Input label="Arama" placeholder="Kampanya, ürün veya market ara" />
            <SelectPlaceholder label="Durum" value="Tüm durumlar" />
            <SelectPlaceholder label="Market" value="Anadolu Market" />
          </div>
        </Card>
        <Card title="Örnek Liste" className="span-8">
          <ProductPreviewTable />
        </Card>
        <Card className="span-4">
          <EmptyState
            title={`${meta.title} ekranı hazırlandı`}
            text="Bu fazda rota, sayfa iskeleti ve temel bileşenler eklendi. Detaylı iş akışı bir sonraki fazda doldurulacak."
            action={
              <Button variant="secondary" href={meta.actionHref}>
                {meta.action}
              </Button>
            }
          />
        </Card>
      </section>
    </>
  );
}
