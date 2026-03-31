"""
Testes unitários para services/plan_validation.py
"""
import pytest
from unittest.mock import MagicMock, patch

from app.services.plan_validation import (
    PlanLimits,
    obter_plano_usuario,
    validar_limite_historico,
    validar_limite_empresas,
    validar_limite_consultas_dia,
    obter_resumo_plano,
)


class TestPlanLimits:
    """Testa definição dos limites de plano"""

    def test_basico_tem_historico_limitado(self):
        assert PlanLimits.BASICO["historico_dias"] == 30

    def test_premium_historico_ilimitado(self):
        assert PlanLimits.PREMIUM["historico_dias"] is None

    def test_enterprise_historico_ilimitado(self):
        assert PlanLimits.ENTERPRISE["historico_dias"] is None

    def test_basico_menos_empresas_que_premium(self):
        assert PlanLimits.BASICO["max_empresas"] < PlanLimits.PREMIUM["max_empresas"]

    def test_premium_menos_empresas_que_enterprise(self):
        assert PlanLimits.PREMIUM["max_empresas"] < PlanLimits.ENTERPRISE["max_empresas"]

    def test_basico_menos_consultas_que_premium(self):
        assert PlanLimits.BASICO["max_consultas_dia"] < PlanLimits.PREMIUM["max_consultas_dia"]


class TestObterPlanoUsuario:
    """Testa obtenção de plano do usuário"""

    @pytest.mark.asyncio
    async def test_retorna_enterprise_em_ambiente_test(self):
        """Em ambiente de teste/dev, deve retornar plano enterprise"""
        mock_db = MagicMock()
        with patch.dict("os.environ", {"ENVIRONMENT": "test"}):
            plano = await obter_plano_usuario("user-uuid", mock_db)
            assert plano["nome"] == "enterprise"

    @pytest.mark.asyncio
    async def test_retorna_enterprise_em_dev(self):
        """Em ambiente de desenvolvimento, deve retornar plano enterprise"""
        mock_db = MagicMock()
        with patch.dict("os.environ", {"ENVIRONMENT": "development"}):
            plano = await obter_plano_usuario("user-uuid", mock_db)
            assert plano["nome"] == "enterprise"

    @pytest.mark.asyncio
    async def test_plano_tem_limites(self):
        mock_db = MagicMock()
        plano = await obter_plano_usuario("user-uuid", mock_db)
        assert "limites" in plano
        assert "historico_dias" in plano["limites"]
        assert "max_empresas" in plano["limites"]

    @pytest.mark.asyncio
    async def test_plano_tem_modulos(self):
        mock_db = MagicMock()
        plano = await obter_plano_usuario("user-uuid", mock_db)
        assert "modulos" in plano
        assert isinstance(plano["modulos"], list)


class TestValidarLimiteHistorico:
    """Testa validação de histórico"""

    @pytest.mark.asyncio
    async def test_ilimitado_sempre_valido(self):
        plano = {"nome": "enterprise", "limites": {"historico_dias": None}}
        resultado = await validar_limite_historico(plano)
        assert resultado is True

    @pytest.mark.asyncio
    async def test_basico_retorna_true(self):
        """Plano básico por enquanto retorna True (implementação futura)"""
        plano = {"nome": "basico", "limites": {"historico_dias": 30}}
        resultado = await validar_limite_historico(plano)
        assert resultado is True

    @pytest.mark.asyncio
    async def test_premium_ilimitado(self):
        plano = {"nome": "premium", "limites": {"historico_dias": None}}
        resultado = await validar_limite_historico(plano)
        assert resultado is True


class TestValidarLimiteEmpresas:
    """Testa validação de limite de empresas"""

    @pytest.mark.asyncio
    async def test_dentro_do_limite(self):
        plano = {"nome": "basico", "limites": {"max_empresas": 3}}
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value\
            .is_.return_value.execute.return_value = MagicMock(count=1)

        resultado = await validar_limite_empresas("user-uuid", plano, mock_db)
        assert resultado is True

    @pytest.mark.asyncio
    async def test_acima_do_limite_levanta_403(self):
        from fastapi import HTTPException
        plano = {"nome": "basico", "limites": {"max_empresas": 3}}
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value\
            .is_.return_value.execute.return_value = MagicMock(count=3)  # No limite = bloqueia

        with pytest.raises(HTTPException) as exc_info:
            await validar_limite_empresas("user-uuid", plano, mock_db)
        assert exc_info.value.status_code == 403


class TestObterResumoPlan:
    """Testa formatação do resumo do plano"""

    def test_resumo_enterprise(self):
        plano = {
            "nome": "enterprise",
            "limites": PlanLimits.ENTERPRISE,
            "modulos": ["nfe_emissao", "nfe_consulta"],
        }
        resumo = obter_resumo_plano(plano)
        assert resumo["nome"] == "ENTERPRISE"
        assert resumo["historico"] == "Ilimitado"

    def test_resumo_basico(self):
        plano = {
            "nome": "basico",
            "limites": PlanLimits.BASICO,
            "modulos": [],
        }
        resumo = obter_resumo_plano(plano)
        assert resumo["nome"] == "BASICO"
        assert "30 dias" in resumo["historico"]

    def test_resumo_tem_campos_obrigatorios(self):
        plano = {
            "nome": "premium",
            "limites": PlanLimits.PREMIUM,
            "modulos": [],
        }
        resumo = obter_resumo_plano(plano)
        for campo in ["nome", "historico", "max_empresas", "max_consultas_dia", "max_notas_mes"]:
            assert campo in resumo, f"Campo '{campo}' ausente no resumo"
