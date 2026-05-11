import pandas as pd
import numpy as np
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import Response, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import os

app = FastAPI(
    title="API de Seleção de Aprovados - PCCE",
    description="API para calcular aprovados em Ampla Concorrência, Negros e PCD com base em um número total."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "resultado_extracao.csv")


def get_clean_data():
    try:
        df = pd.read_csv(CSV_PATH)
        df["Geral"] = pd.to_numeric(df["Geral"], errors="coerce")
        df["Negro"] = pd.to_numeric(df["Negro"], errors="coerce")
        df["PcD"]   = pd.to_numeric(df["PcD"],   errors="coerce")
        return df
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar base de dados: {str(e)}")


def to_json_compatible(df_subset):
    records = df_subset.to_dict(orient="records")
    clean_records = []
    for record in records:
        clean_record = {}
        for key, value in record.items():
            if pd.isna(value) or (isinstance(value, float) and np.isinf(value)):
                clean_record[key] = None
            elif isinstance(value, (np.integer, np.floating)):
                clean_record[key] = value.item()
            else:
                clean_record[key] = value
        clean_records.append(clean_record)
    return clean_records


@app.get("/api")
def home():
    return {
        "status": "online",
        "mensagem": "API de Seleção de Aprovados - PCCE está funcionando!",
        "documentacao": "/docs",
        "exemplo_uso": "/aprovados?total=100"
    }


@app.get("/aprovados")
def calcular_aprovados(total: int = Query(..., gt=0, description="Número total de aprovados desejado")):
    df = get_clean_data()

    qtd_ampla = int(0.75 * total)
    qtd_negro = int(0.20 * total)
    qtd_pcd   = int(0.05 * total)

    # Cada grupo separado pelo Segmento e ordenado pelo seu ranking próprio.
    # Inclui tanto classificados quanto cadastro de reserva, permitindo até 2000+.
    df_ampla = (
        df[df["Segmento"] == "Ampla"]
        .sort_values("Geral")
        .iloc[:qtd_ampla]
    )

    df_negro = (
        df[
            df["Segmento"].str.contains("Negro", case=False, na=False) &
            df["Negro"].notna()
        ]
        .sort_values("Negro")
        .iloc[:qtd_negro]
    )

    df_pcd = (
        df[
            df["Segmento"].str.contains("PcD", case=False, na=False) &
            df["PcD"].notna()
        ]
        .sort_values("PcD")
        .iloc[:qtd_pcd]
    )

    resultado = {
        "configuracao": {
            "total_solicitado": total,
            "vagas_ampla": qtd_ampla,
            "vagas_negro": qtd_negro,
            "vagas_pcd": qtd_pcd
        },
        "resumo_entrega": {
            "total_selecionado": len(df_ampla) + len(df_negro) + len(df_pcd),
            "ampla_selecionados": len(df_ampla),
            "negro_selecionados": len(df_negro),
            "pcd_selecionados": len(df_pcd)
        },
        "listas": {
            "ampla": to_json_compatible(df_ampla),
            "negro": to_json_compatible(df_negro),
            "pcd":   to_json_compatible(df_pcd)
        }
    }

    return Response(
        content=json.dumps(resultado, ensure_ascii=False),
        media_type="application/json"
    )


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
