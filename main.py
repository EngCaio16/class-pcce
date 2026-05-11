import pandas as pd
import numpy as np
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import Response
import json

app = FastAPI(
    title="API de Seleção de Aprovados - PCCE",
    description="API para calcular aprovados em Ampla Concorrência, Negros e PCD com base em um número total."
)

import os
# Caminho absoluto para garantir que o Vercel encontre o arquivo
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "resultado_extracao.csv")

def get_clean_data():
    try:
        df = pd.read_csv(CSV_PATH)
        df["Geral"] = pd.to_numeric(df["Geral"], errors="coerce")
        df["Negro"] = pd.to_numeric(df["Negro"], errors="coerce")
        df["PcD"] = pd.to_numeric(df["PcD"], errors="coerce")
        return df
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar base de dados: {str(e)}")

def to_json_compatible(df_subset):
    """Converte DataFrame para lista de dicionários tratando NaNs e tipos não-JSON."""
    records = df_subset.to_dict(orient="records")
    clean_records = []
    for record in records:
        clean_record = {}
        for key, value in record.items():
            # Tratar NaN, Inf e tipos complexos
            if pd.isna(value) or (isinstance(value, float) and (np.isinf(value))):
                clean_record[key] = None
            elif isinstance(value, (np.integer, np.floating)):
                clean_record[key] = value.item()
            else:
                clean_record[key] = value
        clean_records.append(clean_record)
    return clean_records

@app.get("/aprovados")
def calcular_aprovados(total: int = Query(..., gt=0, description="Número total de aprovados desejado")):
    df = get_clean_data()

    qtd_ampla = int(0.75 * total)
    qtd_negro = int(0.20 * total)
    qtd_pcd = int(0.05 * total)

    df_ampla = df[df["Geral"].notna()].sort_values(by="Geral").iloc[:qtd_ampla]
    df_negro = df[df["Negro"].notna()].sort_values(by="Negro").iloc[:qtd_negro]
    
    df_pcd_base = df[
        (df["Situação"].str.contains("PcD", na=False)) &
        (~df["Pedido"].isin(df_ampla["Pedido"])) &
        (~df["Pedido"].isin(df_negro["Pedido"]))
    ]
    df_pcd = df_pcd_base.iloc[:qtd_pcd]

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
            "pcd": to_json_compatible(df_pcd)
        }
    }

    # Usar json.dumps explicitamente para evitar o erro do serializador do FastAPI
    return Response(
        content=json.dumps(resultado, ensure_ascii=False),
        media_type="application/json"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
