# Design System

## Genel Tasarım Dili

Tasarım, DisKlinikCRM ve Comptario çizgisine yakın bir B2B SaaS arayüzü gibi görünmelidir.

Ana his:

- Temiz
- Kurumsal
- Güven veren
- Operasyonel
- Hızlı kullanılabilir
- Fazla renkli olmayan
- Kart bazlı
- Modern dashboard estetiği

Market broşürü ürünü olduğu için arayüzde canlı kampanya renkleri kullanılabilir; ancak dashboard genelinde aşırı kırmızı/sarı market broşürü görünümü kullanılmamalıdır. Uygulama tarafı kurumsal kalmalı, kampanya görselleri kendi içinde renkli olabilir.

## Renk Paleti

Gerçek DisKlinikCRM / Comptario renkleri farklıysa bu değerler sonradan güncellenebilir.

### Primary

```css
--primary-900: #0F172A;
--primary-800: #1E293B;
--primary-700: #334155;
--primary-600: #2563EB;
--primary-500: #3B82F6;
--primary-100: #DBEAFE;
--primary-50: #EFF6FF;
```

Kullanım:
- Ana buton
- Aktif menü
- Link
- Dashboard vurgu çizgileri
- Grafik ana rengi

### Neutral

```css
--neutral-950: #020617;
--neutral-900: #0F172A;
--neutral-800: #1E293B;
--neutral-700: #334155;
--neutral-600: #475569;
--neutral-500: #64748B;
--neutral-400: #94A3B8;
--neutral-300: #CBD5E1;
--neutral-200: #E2E8F0;
--neutral-100: #F1F5F9;
--neutral-50: #F8FAFC;
--white: #FFFFFF;
```

### Success

```css
--success-700: #047857;
--success-600: #059669;
--success-100: #D1FAE5;
--success-50: #ECFDF5;
```

Kullanım:
- Onaylandı
- Dosya üretildi
- Ürün eşleşti
- Aktif bağlantı

### Warning

```css
--warning-700: #B45309;
--warning-600: #D97706;
--warning-100: #FEF3C7;
--warning-50: #FFFBEB;
```

Kullanım:
- Ürün eksik
- Onay bekliyor
- Düşük eşleşme skoru
- Revizyon bekliyor

### Danger

```css
--danger-700: #B91C1C;
--danger-600: #DC2626;
--danger-100: #FEE2E2;
--danger-50: #FEF2F2;
```

Kullanım:
- Hata
- Eşleşmedi
- Silme işlemi
- PDF üretim hatası

### Campaign Accent

Kampanya/broşür temalı alanlarda sınırlı kullanım için:

```css
--campaign-red: #EF4444;
--campaign-orange: #F97316;
--campaign-yellow: #FACC15;
--campaign-green: #22C55E;
```

Bu renkler dashboard ana UI’da baskın kullanılmamalıdır. Sadece küçük badge, kampanya etiketi veya broşür şablon önizlemelerinde kullanılmalıdır.

## Tipografi

Önerilen font:

- Inter
- Alternatif: Manrope
- Alternatif: system-ui

### Font Ölçekleri

```css
--text-xs: 12px;
--text-sm: 14px;
--text-base: 16px;
--text-lg: 18px;
--text-xl: 20px;
--text-2xl: 24px;
--text-3xl: 30px;
```

### Kullanım

- Sayfa başlığı: 24-30px, semibold/bold
- Kart başlığı: 16-18px, semibold
- Tablo metni: 14px
- Form label: 13-14px, medium
- Yardım metni: 12-13px, neutral-500
- Badge: 12px, medium

## Spacing

8px tabanlı spacing sistemi:

```css
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 20px;
--space-6: 24px;
--space-8: 32px;
--space-10: 40px;
--space-12: 48px;
```

## Radius

```css
--radius-sm: 6px;
--radius-md: 10px;
--radius-lg: 14px;
--radius-xl: 18px;
--radius-2xl: 24px;
```

Kullanım:
- Button: 10px
- Input: 10px
- Card: 14-18px
- Modal: 18-24px
- Badge: 999px

## Shadow

```css
--shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.06);
--shadow-md: 0 8px 24px rgba(15, 23, 42, 0.08);
--shadow-lg: 0 16px 40px rgba(15, 23, 42, 0.12);
```

Kartlarda hafif shadow kullanılmalı. Aşırı gölge kullanılmamalıdır.

## Layout

### Desktop

- Sol sidebar: 260px
- Header yüksekliği: 64px
- İçerik max width: 1440px
- Page padding: 24px veya 32px
- Grid gap: 16px / 24px

### Tablet

- Sidebar collapse olabilir.
- Kartlar 2 kolon olabilir.
- Tablolar yatay scroll alabilir.

### Mobile

- Bottom nav veya drawer sidebar
- Ana aksiyon butonu üstte kalmalı
- Kampanya önizlemesi tek kolon
- Tablo yerine kart liste kullanılmalı

## UI Yoğunluğu

Bu uygulama operasyonel bir dashboard olduğu için gereksiz boşluk çok fazla olmamalı. DisKlinikCRM / Comptario tarzındaki gibi:

- Net header
- Kompakt tablolar
- Açık aksiyon butonları
- Kartlarda yeterli ama abartısız padding
- Sol menüde ikon + metin

## İkon Stili

Önerilen ikon seti:

- Lucide React
- Heroicons
- Tabler Icons

İkonlar çizgisel, sade ve 18-20px olmalıdır.

## Dark Mode

İlk MVP’de zorunlu değildir. Ancak tasarım sistemi dark mode’a uyumlu token yapısında hazırlanabilir.

## Erişilebilirlik

- Ana metin kontrastı yüksek olmalı.
- Button focus state görünür olmalı.
- Hata mesajları sadece renkle anlatılmamalı.
- Form inputları net label taşımalı.
- Dosya yükleme alanları klavye ile erişilebilir olmalı.
