import streamlit as st
from datetime import datetime, timedelta
from PIL import Image
import locale
from math import ceil
from io import BytesIO
import os
import subprocess
import sys
import re

# --- 1. CONFIGURAÇÕES INICIAIS ---
st.set_page_config(layout="wide")

def configure_locale():
    try:
        locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
    except locale.Error:
        try:
            locale.setlocale(locale.LC_ALL, 'pt_BR')
        except locale.Error:
            st.warning("Locale 'pt_BR' não pôde ser configurado.")
            locale.setlocale(locale.LC_ALL, '')
configure_locale()

def install_and_import(package, import_name=None):
    import_name = import_name or package
    try:
        return __import__(import_name)
    except ImportError:
        st.info(f"Instalando {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        return __import__(import_name)

pd = install_and_import('pandas')
FPDF = install_and_import('fpdf2', 'fpdf').FPDF

# --- 2. FUNÇÕES DE CÁLCULO E UTILITÁRIOS ---
@st.cache_data(ttl=86400)
def load_logo():
    try:
        logo = Image.open("JMD HAMOA HORIZONTAL - BRANCO.png")
        logo.thumbnail((300, 300))
        return logo
    except Exception as e:
        st.warning(f"Não foi possível carregar a logo: {str(e)}.")
        return None

def set_theme():
    st.markdown("""
    <style>
        .stApp { background-color: #1E1E1E; }
        h1, h2, h3, h4, h5, h6 { color: #FFFFFF; }
        .stTextInput label, .stNumberInput label, .stSelectbox label, .stDateInput label, .stMultiselect label { color: #FFFFFF !important; }
        .stTextInput input, .stNumberInput input, .stSelectbox select, .stDateInput div[data-baseweb="input"] > div { background-color: #333333; color: #FFFFFF !important; }
        .stMetric { background-color: #252526; border-radius: 8px; padding: 15px; border-left: 4px solid #4D6BFE; }
        .stMetric label { color: #A0A0A0 !important; }
        .dataframe th { background-color: #4D6BFE !important; color: white !important; }
        .stButton button, .stDownloadButton button {
            background-color: #4D6BFE !important; color: white !important; border: none !important; border-radius: 12px !important;
            padding: 10px 24px !important; font-weight: 600 !important; transition: all 0.3s ease !important;
        }
        .stButton button:hover, .stDownloadButton button:hover {
            background-color: #FF4D4D !important; transform: translateY(-2px) !important;
        }
    </style>
    """, unsafe_allow_html=True)

def parse_currency(value_str: str) -> float:
    """Converte uma string de moeda formatada (ex: 'R$ 1.234,56') para float."""
    if not isinstance(value_str, str) or not value_str:
        return 0.0
    try:
        # Remove R$, espaços, e pontos de milhar, depois troca vírgula por ponto decimal
        cleaned_value = re.sub(r'[R$\s\.]', '', value_str).replace(',', '.')
        return float(cleaned_value)
    except (ValueError, TypeError):
        return 0.0

def formatar_moeda(valor, simbolo=True):
    try:
        if valor is None: valor = 0.0
        return locale.currency(valor, grouping=True, symbol=simbolo)
    except Exception:
        return "R$ 0,00"

def calcular_taxas(taxa_mensal_percentual):
    try:
        taxa_mensal_decimal = float(taxa_mensal_percentual or 0.0) / 100
        taxa_anual = ((1 + taxa_mensal_decimal) ** 12) - 1
        taxa_semestral = ((1 + taxa_mensal_decimal) ** 6) - 1
        taxa_diaria = ((1 + taxa_mensal_decimal) ** (1/30.4375)) - 1
        return {'anual': taxa_anual, 'semestral': taxa_semestral, 'mensal': taxa_mensal_decimal, 'diaria': taxa_diaria}
    except: return {'anual': 0, 'semestral': 0, 'mensal': 0, 'diaria': 0}

def calcular_valor_presente(valor_futuro, taxa_diaria, dias):
    try:
        if dias <= 0 or taxa_diaria <= 0: return float(valor_futuro)
        return round(float(valor_futuro) / ((1 + taxa_diaria) ** dias), 2)
    except: return float(valor_futuro or 0.0)

def calcular_fator_vp(datas_vencimento, data_inicio, taxa_diaria):
    if taxa_diaria <= 0: return float(len(datas_vencimento))
    fator_total = 0.0
    for data_venc in datas_vencimento:
        if not isinstance(data_venc, datetime): data_venc = datetime.combine(data_venc, datetime.min.time())
        dias = (data_venc - data_inicio).days
        if dias > 0: fator_total += 1 / ((1 + taxa_diaria) ** dias)
    return fator_total

def ajustar_data_vencimento(data_base, periodo, num_periodo=1, dia_vencimento=None):
    try:
        if not isinstance(data_base, datetime): data_base = datetime.combine(data_base, datetime.min.time())
        ano, mes, dia = data_base.year, data_base.month, dia_vencimento if dia_vencimento is not None else data_base.day
        if periodo == "mensal":
            total_meses = mes + num_periodo; ano += (total_meses - 1) // 12; mes = (total_meses - 1) % 12 + 1
        elif periodo == "semestral":
            total_meses = mes + (6 * num_periodo); ano += (total_meses - 1) // 12; mes = (total_meses - 1) % 12 + 1
        elif periodo == "anual": ano += num_periodo
        ultimo_dia_do_mes = (datetime(ano, (mes % 12) + 1, 1) - timedelta(days=1)).day if mes < 12 else 31
        dia_final = min(dia, ultimo_dia_do_mes)
        return datetime(ano, mes, dia_final)
    except Exception: return data_base + timedelta(days=30 * num_periodo)

def determinar_modo_calculo(modalidade):
    return {"mensal": 1, "mensal + balão": 2, "só balão anual": 3, "só balão semestral": 4}.get(modalidade, 1)

def atualizar_baloes(modalidade, qtd_parcelas, tipo_balao=None):
    try:
        qtd_parcelas = int(qtd_parcelas or 0)
        if modalidade == "mensal + balão":
            intervalo = 12 if tipo_balao == "anual" else 6
            return qtd_parcelas // intervalo if intervalo > 0 else 0
        elif modalidade == "só balão anual": return max(ceil(qtd_parcelas / 12), 0)
        elif modalidade == "só balão semestral": return max(ceil(qtd_parcelas / 6), 0)
        return 0
    except (ValueError, TypeError): return 0

@st.cache_data(ttl=3600)
def gerar_cronograma(valor_financiado, valor_parcela_final, valor_balao_final,
                      qtd_parcelas, qtd_baloes, modalidade, tipo_balao,
                      data_entrada, taxas, agendamento_baloes, meses_baloes, mes_primeiro_balao):
    try:
        dia_vencimento = data_entrada.day
        cronograma = []
        if modalidade in ["mensal", "mensal + balão"]:
            for i in range(1, qtd_parcelas + 1):
                data_vencimento = ajustar_data_vencimento(data_entrada, "mensal", i, dia_vencimento)
                dias = (data_vencimento - data_entrada).days
                vp = calcular_valor_presente(valor_parcela_final, taxas['diaria'], dias)
                cronograma.append({"Item": f"Parcela {i}", "Tipo": "Parcela", "Data_Vencimento": data_vencimento.strftime('%d/%m/%Y'), "Dias": dias, "Valor": round(valor_parcela_final, 2), "Valor_Presente": round(vp, 2), "Desconto_Aplicado": round(valor_parcela_final - vp, 2)})
        
        datas_baloes_a_gerar = []
        periodo_map = {"só balão anual": "anual", "só balão semestral": "semestral"}
        if modalidade in periodo_map:
            periodo = periodo_map[modalidade]
            datas_baloes_a_gerar = [ajustar_data_vencimento(data_entrada, periodo, i, dia_vencimento) for i in range(1, qtd_baloes + 1)]
        elif modalidade == "mensal + balão" and qtd_baloes > 0:
            if agendamento_baloes == "Personalizado (Mês a Mês)":
                datas_baloes_a_gerar = [ajustar_data_vencimento(data_entrada, "mensal", mes, dia_vencimento) for mes in meses_baloes]
            elif agendamento_baloes == "A partir do 1º Vencimento":
                data_base_balao = ajustar_data_vencimento(data_entrada, "mensal", mes_primeiro_balao, dia_vencimento)
                datas_baloes_a_gerar = [ajustar_data_vencimento(data_base_balao, tipo_balao, i) for i in range(qtd_baloes)]
            else:
                intervalo = 12 if tipo_balao == "anual" else 6
                datas_baloes_a_gerar = [ajustar_data_vencimento(data_entrada, "mensal", i * intervalo, dia_vencimento) for i in range(1, qtd_baloes + 1)]

        for i, data_vencimento in enumerate(datas_baloes_a_gerar):
            balao_count = i + 1
            dias = (data_vencimento - data_entrada).days
            vp = calcular_valor_presente(valor_balao_final, taxas['diaria'], dias)
            cronograma.append({"Item": f"Balão {balao_count}", "Tipo": "Balão", "Data_Vencimento": data_vencimento.strftime('%d/%m/%Y'), "Dias": dias, "Valor": round(valor_balao_final, 2), "Valor_Presente": round(vp, 2), "Desconto_Aplicado": round(valor_balao_final - vp, 2)})
        
        cronograma.sort(key=lambda x: datetime.strptime(x['Data_Vencimento'], '%d/%m/%Y') if x.get('Data_Vencimento') else datetime.min)
        
        if cronograma:
            total_vp_calculado = sum(p['Valor_Presente'] for p in cronograma)
            diferenca = round(valor_financiado - total_vp_calculado, 2)
            if diferenca != 0:
                cronograma[0]['Valor'] = round(cronograma[0]['Valor'] + diferenca, 2)
                cronograma[0]['Valor_Presente'] = round(cronograma[0]['Valor_Presente'] + diferenca, 2)
                cronograma[0]['Desconto_Aplicado'] = round(cronograma[0]['Valor'] - cronograma[0]['Valor_Presente'], 2)

            total_valor = round(sum(p['Valor'] for p in cronograma), 2)
            total_vp = round(sum(p['Valor_Presente'] for p in cronograma), 2)
            cronograma.append({"Item": "TOTAL", "Tipo": "", "Data_Vencimento": "", "Dias": "", "Valor": total_valor, "Valor_Presente": total_vp, "Desconto_Aplicado": round(total_valor - total_vp, 2)})
        
        return cronograma
    except Exception as e:
        st.error(f"Erro ao gerar cronograma: {str(e)}."); return []

def gerar_pdf(cronograma, dados):
    try:
        pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 14)
        pdf.cell(200, 10, txt="Informações do Imóvel", ln=1, align='L'); pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"Quadra: {dados.get('quadra', 'N/I')}", ln=1); pdf.cell(200, 10, txt=f"Lote: {dados.get('lote', 'N/I')}", ln=1); pdf.cell(200, 10, txt=f"Metragem: {dados.get('metragem', 'N/I')} m²", ln=1)
        pdf.ln(5); pdf.set_font("Arial", 'B', 14)
        pdf.cell(200, 10, txt="Simulação de Financiamento", ln=1, align='L'); pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"Valor Total do Imóvel: {formatar_moeda(dados['valor_total'])}", ln=1); pdf.cell(200, 10, txt=f"Entrada: {formatar_moeda(dados['entrada'])}", ln=1); pdf.cell(200, 10, txt=f"Valor Financiado: {formatar_moeda(dados['valor_financiado'])}", ln=1); pdf.cell(200, 10, txt=f"Taxa Mensal Utilizada: {dados['taxa_mensal']:.2f}%", ln=1)
        pdf.ln(10); pdf.set_font("Arial", 'B', 12)
        colunas = ["Item", "Tipo", "Data Venc.", "Valor", "Valor Presente", "Desconto Aplicado"]; larguras = [30, 25, 30, 35, 35, 35]
        for col, larg in zip(colunas, larguras): pdf.cell(larg, 10, txt=col, border=1, align='C')
        pdf.ln(); pdf.set_font("Arial", size=10)
        cronograma_sem_total = [p for p in cronograma if p['Item'] != 'TOTAL']
        for item in cronograma_sem_total:
            pdf.cell(larguras[0], 8, txt=str(item['Item']), border=1); pdf.cell(larguras[1], 8, txt=str(item['Tipo']), border=1); pdf.cell(larguras[2], 8, txt=str(item['Data_Vencimento']), border=1)
            pdf.cell(larguras[3], 8, txt=formatar_moeda(item['Valor'], simbolo=False), border=1, align='R'); pdf.cell(larguras[4], 8, txt=formatar_moeda(item['Valor_Presente'], simbolo=False), border=1, align='R'); pdf.cell(larguras[5], 8, txt=formatar_moeda(item['Desconto_Aplicado'], simbolo=False), border=1, align='R'); pdf.ln()
        total = next((p for p in cronograma if p['Item'] == 'TOTAL'), None)
        if total:
            pdf.set_font("Arial", 'B', 10); pdf.cell(sum(larguras[:3]), 10, txt="TOTAL", border=1, align='R')
            pdf.cell(larguras[3], 10, txt=formatar_moeda(total['Valor'], simbolo=False), border=1, align='R'); pdf.cell(larguras[4], 10, txt=formatar_moeda(total['Valor_Presente'], simbolo=False), border=1, align='R'); pdf.cell(larguras[5], 10, txt=formatar_moeda(total['Desconto_Aplicado'], simbolo=False), border=1, align='R')
        return BytesIO(pdf.output())
    except Exception as e:
        st.error(f"Erro ao gerar PDF: {str(e)}"); return BytesIO()

def gerar_excel(cronograma, dados):
    try:
        install_and_import('openpyxl'); output = BytesIO()
        info_df = pd.DataFrame({'Campo': ['Quadra', 'Lote', 'Metragem', 'Valor Total do Imóvel', 'Entrada', 'Valor Financiado', 'Taxa Mensal Utilizada'], 'Valor': [dados.get('quadra', 'N/I'), dados.get('lote', 'N/I'), f"{dados.get('metragem', 'N/I')} m²", formatar_moeda(dados.get('valor_total', 0)), formatar_moeda(dados.get('entrada', 0)), formatar_moeda(dados.get('valor_financiado', 0)), f"{dados.get('taxa_mensal', 0):.2f}%"]})
        df_cronograma_data = pd.DataFrame([p for p in cronograma if p['Item'] != 'TOTAL'])
        total_row = next((p for p in cronograma if p['Item'] == 'TOTAL'), None)
        df_final = pd.concat([df_cronograma_data, pd.DataFrame([total_row])], ignore_index=True) if total_row else df_cronograma_data
        df_export = df_final[['Item', 'Tipo', 'Data_Vencimento', 'Valor', 'Valor_Presente', 'Desconto_Aplicado']]
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            info_df.to_excel(writer, sheet_name='Informações da Simulação', index=False)
            df_export.to_excel(writer, sheet_name='Cronograma de Pagamentos', index=False)
        output.seek(0); return output
    except Exception as e:
        st.error(f"Erro ao gerar Excel: {str(e)}"); return BytesIO()
    
def main():
    set_theme()
    
    if 'taxa_mensal' not in st.session_state: st.session_state.taxa_mensal = 0.89
    
    def reset_form():
        st.session_state.clear()
        st.session_state.taxa_mensal = 0.89

    logo = load_logo()
    if logo:
        col1, col2 = st.columns([1, 4]); col1.image(logo, width=200); col2.title("**Bem-vindo ao Simulador da JMD HAMOA**")
    else:
        st.title("Simulador Imobiliário")

    st.text_input("Quadra", key="quadra", placeholder="Ex: 15")
    st.text_input("Lote", key="lote", placeholder="Ex: 22")
    st.text_input("Metragem (m²)", key="metragem", placeholder="Ex: 360")

    with st.form("simulador_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            valor_total_str = st.text_input("Valor Total do Imóvel (R$)", key="valor_total_str", placeholder="Ex: 150.000,50")
            entrada_str = st.text_input("Entrada (R$)", key="entrada_str", placeholder="Ex: 20.000,00")
            data_input = st.date_input("Data de Entrada", value=datetime.now(), format="DD/MM/YYYY", key="data_input")
            taxa_mensal = st.number_input("Taxa de Juros Mensal (%)", value=st.session_state.taxa_mensal, step=0.01, format="%.2f", key="taxa_mensal_input", help="Use vírgula para decimais (ex: 0,79).")
            modalidade = st.selectbox("Modalidade de Pagamento", ["mensal", "mensal + balão", "só balão anual", "só balão semestral"], key="modalidade")
            
        with col2:
            qtd_parcelas = st.number_input("Quantidade de Parcelas", min_value=0, max_value=360, step=1, key="qtd_parcelas", placeholder="Ex: 180")
            valor_parcela_str = st.text_input("Valor da Parcela (R$)", key="valor_parcela_str", placeholder="Deixe em branco para cálculo")
            valor_balao_str = ""
            
            tipo_balao = "anual" if "anual" in modalidade else "semestral"
            agendamento_baloes = "Padrão"
            if modalidade == "mensal + balão":
                tipo_balao = st.selectbox("Período Padrão do Balão:", ["anual", "semestral"], key="tipo_balao")
                agendamento_baloes = st.selectbox("Agendamento dos Balões", ["Padrão", "A partir do 1º Vencimento", "Personalizado (Mês a Mês)"], key="agendamento_baloes")
                max_p = st.session_state.get('qtd_parcelas', 360) or 1
                if agendamento_baloes == "Personalizado (Mês a Mês)":
                    st.multiselect("Selecione os meses dos balões:", options=list(range(1, max_p + 1)), key="meses_baloes")
                elif agendamento_baloes == "A partir do 1º Vencimento":
                    st.number_input("Mês de Vencimento do 1º Balão", min_value=1, max_value=max_p, value=12, step=1, key="mes_primeiro_balao")
                
                qtd_baloes_calculado = atualizar_baloes(modalidade, qtd_parcelas, tipo_balao)
                if agendamento_baloes == "Personalizado (Mês a Mês)":
                    qtd_baloes_calculado = len(st.session_state.get('meses_baloes', []))
                st.write(f"Quantidade de Balões: **{qtd_baloes_calculado}**")
                valor_balao_str = st.text_input("Valor do Balão (R$)", key="valor_balao_str", placeholder="Deixe em branco para cálculo")

        submitted = st.form_submit_button("Calcular")
        st.form_submit_button("Reiniciar", on_click=reset_form)
    
    if submitted:
        try:
            st.session_state.taxa_mensal = taxa_mensal
            valor_total = parse_currency(valor_total_str)
            entrada = parse_currency(entrada_str)
            valor_parcela = parse_currency(valor_parcela_str)
            valor_balao = parse_currency(valor_balao_str)
            
            taxa_mensal_para_calculo = taxa_mensal if not (1 <= (qtd_parcelas or 0) <= 36 and modalidade == 'mensal') else 0.0
            if valor_total <= 0 or entrada < 0 or valor_total <= entrada:
                st.error("Verifique os valores de 'Total do Imóvel' e 'Entrada'."); return
            
            valor_financiado = round(max(valor_total - entrada, 0), 2)
            taxas = calcular_taxas(taxa_mensal_para_calculo)
            modo = determinar_modo_calculo(modalidade)
            data_entrada = datetime.combine(data_input, datetime.min.time())

            meses_baloes = st.session_state.get('meses_baloes', [])
            mes_primeiro_balao = st.session_state.get('mes_primeiro_balao', 12)
            
            qtd_baloes = atualizar_baloes(modalidade, qtd_parcelas, tipo_balao)
            if modalidade == "mensal + balão" and agendamento_baloes == "Personalizado (Mês a Mês)":
                qtd_baloes = len(meses_baloes)
            
            valor_parcela_final, valor_balao_final = 0.0, 0.0
            
            datas_p = [ajustar_data_vencimento(data_entrada, "mensal", i) for i in range(1, (qtd_parcelas or 0) + 1)]
            datas_b = []
            if qtd_baloes > 0:
                if modalidade in ["só balão anual", "só balão semestral"]:
                    periodo = "anual" if modalidade == "só balão anual" else "semestral"
                    datas_b = [ajustar_data_vencimento(data_entrada, periodo, i) for i in range(1, qtd_baloes + 1)]
                elif modalidade == "mensal + balão":
                    if agendamento_baloes == "Personalizado (Mês a Mês)": datas_b = [ajustar_data_vencimento(data_entrada, "mensal", m) for m in meses_baloes]
                    elif agendamento_baloes == "A partir do 1º Vencimento":
                        base = ajustar_data_vencimento(data_entrada, "mensal", mes_primeiro_balao)
                        datas_b = [ajustar_data_vencimento(base, tipo_balao, i) for i in range(qtd_baloes)]
                    else:
                        intervalo = 12 if tipo_balao == 'anual' else 6
                        datas_b = [ajustar_data_vencimento(data_entrada, "mensal", i * intervalo) for i in range(1, qtd_baloes + 1)]

            fator_vp_p = calcular_fator_vp(datas_p, data_entrada, taxas['diaria'])
            fator_vp_b = calcular_fator_vp(datas_b, data_entrada, taxas['diaria'])

            if modo == 1: valor_parcela_final = round(valor_financiado / fator_vp_p, 2) if fator_vp_p > 0 else 0
            elif modo in [3, 4]: valor_balao_final = round(valor_financiado / fator_vp_b, 2) if fator_vp_b > 0 else 0
            elif modo == 2:
                if valor_parcela > 0 and valor_balao == 0:
                    valor_parcela_final = valor_parcela; vp_restante = max(valor_financiado - (valor_parcela * fator_vp_p), 0)
                    valor_balao_final = round(vp_restante / fator_vp_b, 2) if fator_vp_b > 0 else 0
                elif valor_balao > 0 and valor_parcela == 0:
                    valor_balao_final = valor_balao; vp_restante = max(valor_financiado - (valor_balao * fator_vp_b), 0)
                    valor_parcela_final = round(vp_restante / fator_vp_p, 2) if fator_vp_p > 0 else 0
                else: st.error("No modo 'mensal + balão', preencha OU o valor da parcela OU o valor do balão."); return

            cronograma = gerar_cronograma(valor_financiado, valor_parcela_final, valor_balao_final, (qtd_parcelas or 0), qtd_baloes, modalidade, tipo_balao, data_entrada, taxas, agendamento_baloes, meses_baloes, mes_primeiro_balao)
            
            st.subheader("Resultados da Simulação")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Valor Financiado", formatar_moeda(valor_financiado))
            c2.metric("Taxa Mensal Utilizada", f"{taxa_mensal_para_calculo:.2f}%")
            if cronograma and len(cronograma) > 1:
                primeira_parcela = next((p for p in cronograma if p['Tipo'] == 'Parcela'), None)
                primeiro_balao = next((p for p in cronograma if p['Tipo'] == 'Balão'), None)
                if primeira_parcela: c3.metric("Valor da Parcela", formatar_moeda(primeira_parcela['Valor']))
                if primeiro_balao: c4.metric("Valor do Balão", formatar_moeda(primeiro_balao['Valor']))

            st.subheader("Cronograma de Pagamentos")
            if cronograma:
                df_cronograma = pd.DataFrame([p for p in cronograma if p['Item'] != 'TOTAL'])
                st.dataframe(df_cronograma.style.format({'Valor': 'R$ {:,.2f}', 'Valor_Presente': 'R$ {:,.2f}', 'Desconto_Aplicado': 'R$ {:,.2f}'}), use_container_width=True, hide_index=True)
                total = cronograma[-1]
                c1_res, c2_res, c3_res = st.columns(3)
                c1_res.metric("Valor Total a Pagar", formatar_moeda(total['Valor'])); c2_res.metric("Valor Presente Total", formatar_moeda(total['Valor_Presente'])); c3_res.metric("Total de Descontos", formatar_moeda(total['Desconto_Aplicado']))
                
                st.subheader("Exportar Resultados")
                export_data = {'valor_total': valor_total, 'entrada': entrada, 'taxa_mensal': taxa_mensal_para_calculo, 'valor_financiado': valor_financiado, 'quadra': st.session_state.quadra, 'lote': st.session_state.lote, 'metragem': st.session_state.metragem}
                c1_exp, c2_exp = st.columns(2)
                pdf_file = gerar_pdf(cronograma, export_data); c1_exp.download_button("Exportar para PDF", pdf_file, "simulacao.pdf", "application/pdf")
                excel_file = gerar_excel(cronograma, export_data); c2_exp.download_button("Exportar para Excel", excel_file, "simulacao.xlsx")

        except Exception as e:
            st.error(f"Ocorreu um erro na simulação: {e}")

if __name__ == '__main__':
    main()
