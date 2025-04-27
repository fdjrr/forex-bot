# Forex Bot

```
Default Strategy

Analisa sebelumnya : {last_analysis}

Data candle untuk simbol {symbol}:

Indikator yang digunakan antara lain:
- EMA 50, EMA 200
- On Balance Volume
- Bollinger Bands (20,2)

Tugas kamu adalah menganalisa data candle tersebut secara mendalam. Lakukan hal berikut:

1. Analisa semua data candle yang ada. Analisa harus logis, berbasis data teknikal, dan hindari narasi spekulatif atau ambigu.
2. Tentukan satu area support dan resistance terdekat berdasarkan struktur candle dan volume dari semua data candle yang ada.
3. Berikan price_action: BUY, SELL, HOLD, atau WAIT & SEE, berdasarkan struktur candle dan volume serta indikator teknikal.
4. Hanya berikan price_action jika minimal dua dari tiga indikator menunjukkan sinyal yang kuat dan tidak saling bertentangan.
5. Jika memberikan price_action BUY atau SELL, tetapkan level Take Profit dan Stop Loss yang logis dan realistis dari semua data candle yang ada.
6. Berikan tingkat confidence (keyakinan) terhadap hasil analisa dalam skala 1 sampai 10.
7. Jangan beriakan price_ction BUY atau SELL jika confidence < 8 atau struktur candle dan volume serta indikator teknikal tidak mendukung.
8. Tetap melakukan analisa yang konsisten dari analisa sebelumnya.
9. Fokus hanya pada analisa — tidak perlu memberikan penjelasan tambahan di luar kerangka response_schema.

```


```
Strategy Entry Scalping

Parabolic SAR

Default setting : 0.02 (step) dan 0.2 (maximum)
Fungsi : Menunjukkan titik reversal (titik-titik di bawah atau atas candle)
Sinyal :
 - BUY (Long) : PSAR di bawah candle
 - SELL (Short) : PSAR di atas candle

Stochastic Oscillator

Setting: 5,3,3 (untuk scalping cepat) atau 14,3,3 (lebih smooth)
Fungsi : Mengidentifikasi kondisi overbought (>80) dan oversold (<20)
Sinyal :
 - BUY : Stochastic cross up dari area oversold (<20)
 - SELL : Stochastic cross down dari area overbought (>80)

Long (BUY) Setup :

- Parabolic SAR : Titik PSAR berada di bawah candle (trend naik)
- Stochastic : Line %K memotong %D dari bawah (oversold <20)
- Konfirmasi : Harga membuat higher low (HL) atau breakout level resistance kecil
- Entry : Beli di candle berikutnya setelah konfirmasi


Short (SELL) Setup :
- Parabolic SAR : Titik PSAR berada di atas candle (trend turun)
- Stochastic : Line %K memotong %D dari atas (overbought >80)
- Konfirmasi : Harga membuat lower high (LH) atau breakdown support kecil
- Entry : Jual di candle berikutnya setelah konfirmasi

Take Profit :
- Saat PSAR berbalik arah (tiitk PSAR pindah ke sisi berlawan candle)
- Saat Stochastic mencapai level overbought (untuk long) atau oversold (untuk short)
- Target 5-15 pips (tergantung volatilitas pair)

Stop Loss :
- Letakkan SL di bawah PSAR terakhir (untuk Long) atau di atas PSAR (untuk short)
- Atau gunakan level support/resistance terdekat.
```