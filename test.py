import pandas as pd
from ollama import chat


def main():
    with open("results/XAUUSDm.csv", "r") as f:
        csv_text = f.read()

    content = f"""
        {csv_text}

        Berikut ini adalah data harga untuk simbol XAUUSDm untuk timeframe M1 dan M5:

        Indikator yang digunakan :

        df["MA_3"] = SMAIndicator(close=df["close"], window=3).sma_indicator()
        df["EMA_8"] = EMAIndicator(close=df["close"], window=8).ema_indicator()
        df["RSI_3"] = RSIIndicator(close=df["close"], window=3).rsi()
        stoch = StochasticOscillator(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            window=3,
            smooth_window=2,
        )
        df["Stoch_%K"] = stoch.stoch()
        df["Stoch_%D"] = stoch.stoch_signal()
        df["ATR_5"] = AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=5
        ).average_true_range()
        df["Buy_Signal_ATR"] = (
            (df["close"] > df["high"].shift(1) + df["ATR_5"].shift(1))
        ).astype(int)
        df["Sell_Signal_ATR"] = (
            (df["close"] < df["low"].shift(1) - df["ATR_5"].shift(1))
        ).astype(int)
        df["CCI_10"] = CCIIndicator(
            high=df["high"], low=df["low"], close=df["close"], window=10
        ).cci()
        adx = ADXIndicator(high=df["high"], low=df["low"], close=df["close"], window=7)
        df["ADX"] = adx.adx()
        df["ADX_Pos"] = adx.adx_pos()
        df["ADX_Neg"] = adx.adx_neg()
        df["AO"] = AwesomeOscillatorIndicator(
            high=df["high"], low=df["low"]
        ).awesome_oscillator()
        df["Momentum_5"] = ROCIndicator(close=df["close"], window=5).roc()
        macd = MACD(close=df["close"], window_slow=21, window_fast=8, window_sign=5)
        df["MACD"] = macd.macd()
        df["MACD_Signal"] = macd.macd_signal()
        df["MACD_Hist"] = macd.macd_diff()
        stoch_rsi = StochRSIIndicator(
            close=df["close"], window=7, smooth1=2, smooth2=2
        )
        df["Stoch_RSI"] = stoch_rsi.stochrsi()
        df["Stoch_RSI_K"] = stoch_rsi.stochrsi_k()
        df["Stoch_RSI_D"] = stoch_rsi.stochrsi_d()
        df["Williams_%R"] = WilliamsRIndicator(
            high=df["high"], low=df["low"], close=df["close"], lbp=14
        ).williams_r()
        df["Bull_Bear_Power"] = ForceIndexIndicator(
            close=df["close"], volume=df["real_volume"], window=2
        ).force_index()
        df["Ultimate_Osc"] = UltimateOscillator(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            window1=3,
            window2=7,
            window3=14,
        ).ultimate_oscillator()

        Tugas kamu adalah menganalisa data tersebut secara mendalam. Lakukan hal berikut:

        1. Tentukan area **support** dan **resistance** berdasarkan data yang tersedia.
        2. Berikan penilaian tingkat **volatilitas** pasar dalam skala 1 sampai 100.
        3. Rekomendasikan apakah sebaiknya **BUY**, **SELL**, **WAIT & SEE**, atau **HOLD** pada kondisi saat ini.
        4. Tentukan area **TAKE PROFIT** dan **STOP LOSS** jika kamu merekomendasikan **BUY** atau **SELL**
        5. Analisa harus **logis** dan **berdasarkan data** yang tersedia.
        6. Berikan tingkat **confidence** (keyakinan) yang kuat terhadap hasil analisa tersebut dalam skala 1 sampai 100.
        7. Jangan gunakan kata 'disclaimer', peringatan risiko, atau kalimat yang bersifat umum/ambigu atau frasa yang tidak relevan dengan analisa teknikal.
        8. Jawaban harus spesifik dan berdasarkan data harga yang diberikan.
        9. Jawaban hanya dalam format yang sesuai dengan skema response_schema yang telah ditentukan.
    """

    response = chat(
        model="deepseek-r1:1.5b",
        messages=[
            {
                "role": "user",
                "content": content,
            },
        ],
    )

    print(response["message"]["content"])


if __name__ == "__main__":
    main()
