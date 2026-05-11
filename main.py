import pandas as pd
import numpy as np
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import Response, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import os

app = FastAPI(
    title="API de Seleção de Aprovados - PCCE",
    description="API para calcular aprovados com sistema de cotas estrito a 5% para PcD e reversão total de vagas remanescentes para Ampla Concorrência."
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
    if not os.path.exists(CSV_PATH):
        raise HTTPException(status_code=500, detail="Arquivo CSV não encontrado no servidor.")
    try:
        df = pd.read_csv(CSV_PATH)
        df["Geral"] = pd.to_numeric(df["Geral"], errors="coerce")
        df["Negro"] = pd.to_numeric(df["Negro"], errors="coerce")
        df["PcD"]   = pd.to_numeric(df["PcD"],   errors="coerce")
        return df
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar base de dados: {str(e)}")

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

    # 1. Definição estrita das fatias conforme percentuais
    qtd_ampla = int(0.75 * total)
    qtd_negro = int(0.20 * total)
    qtd_pcd   = int(0.05 * total)  # Mantido estritamente em 5%

    # --- EXECUÇÃO DAS FILTRAGENS ---

    # A. Seleção Inicial da Ampla
    df_ampla = (
        df[df["Geral"].notna()]
        .sort_values(by="Geral")
        .iloc[:qtd_ampla]
    )

    # B. Seleção de Negros
    df_negro = (
        df[
            df["Negro"].notna() & 
            (~df["Pedido"].isin(df_ampla["Pedido"]))
        ]
        .sort_values(by="Negro")
        .iloc[:qtd_negro]
    )

    # C. Seleção de PcD
    df_pcd = (
        df[
            df["Situação"].str.contains("PcD", na=False) & 
            (~df["Pedido"].isin(df_ampla["Pedido"])) & 
            (~df["Pedido"].isin(df_negro["Pedido"]))
        ]
        .iloc[:qtd_pcd]
    )

    # --- LÓGICA DE COMPENSAÇÃO NA AMPLA CONCORRÊNCIA ---
    # Se a soma dos selecionados (incluindo quebras de arredondamento ou falta de cotistas)
    # for menor que o total solicitado pelo usuário, a Ampla absorve a diferença.
    total_parcial = len(df_ampla) + len(df_negro) + len(df_pcd)
    vagas_remanescentes = total - total_parcial

    if vagas_remanescentes > 0:
        selecionados_ids = pd.concat([df_ampla["Pedido"], df_negro["Pedido"], df_pcd["Pedido"]])
        
        df_complemento = (
            df[df["Geral"].notna() & (~df["Pedido"].isin(selecionados_ids))]
            .sort_values(by="Geral")
            .iloc[:vagas_remanescentes]
        )
        
        # A Ampla absorve todos os remanescentes
        df_ampla = pd.concat([df_ampla, df_complemento])

    # --- MONTAGEM DO RESULTADO FINAL ---
    resultado = {
        "configuracao_vagas": {
            "total_solicitado": total,
            "distribuicao_teorica": {
                "ampla": qtd_ampla,
                "negro": qtd_negro,
                "pcd": qtd_pcd
            }
        },
        "resumo_entrega": {
            "total_selecionado": len(df_ampla) + len(df_negro) + len(df_pcd),
            "ampla_final": len(df_ampla),
            "negro_final": len(df_negro),
            "pcd_final": len(df_pcd),
            "vagas_remanescentes_revertidas_para_ampla": int(vagas_remanescentes)
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
    path_index = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(path_index):
        return FileResponse(path_index)
    return {"erro": "index.html não encontrado na raiz do projeto"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
