import { Badge } from "./Badge.jsx";

const statusToneMap = {
  Taslak: "neutral",
  "Analiz ediliyor": "primary",
  "Ürünler eşleştiriliyor": "primary",
  "Eksik ürün var": "warning",
  "Önizleme hazır": "primary",
  "Onay bekliyor": "warning",
  "Revizyon istendi": "warning",
  Onaylandı: "success",
  "Dosyalar üretiliyor": "primary",
  Tamamlandı: "success",
  "Hata oluştu": "danger",
  "İptal edildi": "neutral",
  Eşleşti: "success",
  "Kontrol gerekli": "warning",
  Bulunamadı: "danger",
  "Manuel seçildi": "primary",
  "Yeni ürün gerekli": "danger",
  Aktif: "success",
  Pasif: "neutral",
  Hazır: "success",
  Bekliyor: "warning",
  "MVP hazır": "success",
  Sağlıklı: "success",
  "Kurulu değil": "warning",
};

export function StatusBadge({ status }) {
  return <Badge tone={statusToneMap[status] || "neutral"}>{status}</Badge>;
}
