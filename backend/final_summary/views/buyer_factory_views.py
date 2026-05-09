"""
------------------------------
Registration endpoints for Buyer, Factory, and BuyerFactoryPair.

These must be registered BEFORE uploading any Excel files.

Endpoints
---------
GET/POST   /api/final-summary/buyers/
GET/PUT    /api/final-summary/buyers/<pk>/

GET/POST   /api/final-summary/factories/
GET/PUT    /api/final-summary/factories/<pk>/

GET/POST   /api/final-summary/pairs/
GET/PUT    /api/final-summary/pairs/<pk>/

GET        /api/final-summary/pairs/options/
  Returns all active buyers, factories, report types and available report
  choices — used to populate the upload form dropdowns.
"""

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from final_summary.models import (
    Buyer,
    Factory,
    BuyerFactoryPair,
    AvailableReport,
    ReportType,
)
from final_summary.serializers import (
    BuyerSerializer,
    FactorySerializer,
    BuyerFactoryPairSerializer,
)


# ── Buyer ─────────────────────────────────────────────────────────────────────

class BuyerListCreateView(generics.ListCreateAPIView):
    """GET list / POST create a buyer."""
    permission_classes = [IsAuthenticated]
    serializer_class   = BuyerSerializer
    queryset           = Buyer.objects.filter(is_active=True).order_by("name")


class BuyerDetailView(generics.RetrieveUpdateAPIView):
    """GET / PUT a single buyer."""
    permission_classes = [IsAuthenticated]
    serializer_class   = BuyerSerializer
    queryset           = Buyer.objects.all()


# ── Factory ───────────────────────────────────────────────────────────────────

class FactoryListCreateView(generics.ListCreateAPIView):
    """GET list / POST create a factory. Filter by ?buyer=<id>."""
    permission_classes = [IsAuthenticated]
    serializer_class   = FactorySerializer

    def get_queryset(self):
        qs = Factory.objects.select_related("buyer").filter(is_active=True)
        buyer_id = self.request.query_params.get("buyer")
        if buyer_id:
            qs = qs.filter(buyer_id=buyer_id)
        return qs.order_by("buyer__name", "name")


class FactoryDetailView(generics.RetrieveUpdateAPIView):
    """GET / PUT a single factory."""
    permission_classes = [IsAuthenticated]
    serializer_class   = FactorySerializer
    queryset           = Factory.objects.select_related("buyer").all()


# ── BuyerFactoryPair ──────────────────────────────────────────────────────────

class PairListCreateView(generics.ListCreateAPIView):
    """GET list / POST create a buyer–factory pair."""
    permission_classes = [IsAuthenticated]
    serializer_class   = BuyerFactoryPairSerializer

    def get_queryset(self):
        qs = BuyerFactoryPair.objects.select_related(
            "buyer", "factory"
        ).filter(is_active=True)
        buyer_id = self.request.query_params.get("buyer")
        if buyer_id:
            qs = qs.filter(buyer_id=buyer_id)
        return qs.order_by("buyer__name", "factory__name")


class PairDetailView(generics.RetrieveUpdateAPIView):
    """GET / PUT a single pair."""
    permission_classes = [IsAuthenticated]
    serializer_class   = BuyerFactoryPairSerializer
    queryset           = BuyerFactoryPair.objects.select_related(
        "buyer", "factory"
    ).all()


# ── Upload form options ───────────────────────────────────────────────────────

class PairOptionsView(APIView):
    """
    GET /api/final-summary/pairs/options/

    Returns all data needed to populate the upload form:
      - buyers          : [{id, name, code}]
      - factories       : [{id, name, buyer_id}]  (all active)
      - pairs           : [{id, buyer_id, factory_id, report_type, available_reports}]
      - report_types    : [{value, label}]
      - report_choices  : [{value, label}]
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        buyers = list(
            Buyer.objects.filter(is_active=True)
            .order_by("name")
            .values("id", "name", "code")
        )
        factories = list(
            Factory.objects.filter(is_active=True)
            .select_related("buyer")
            .order_by("name")
            .values("id", "name", "buyer_id", "buyer__name", "country")
        )
        pairs = list(
            BuyerFactoryPair.objects.filter(is_active=True)
            .select_related("buyer", "factory")
            .order_by("buyer__name", "factory__name")
            .values(
                "id", "buyer_id", "factory_id",
                "report_type", "available_reports",
                "buyer__name", "factory__name",
                "notes",
            )
        )

        return Response({
            "buyers":         buyers,
            "factories":      factories,
            "pairs":          pairs,
            "report_types":   [
                {"value": c[0], "label": c[1]}
                for c in ReportType.choices
            ],
            "report_choices": [
                {"value": c[0], "label": c[1]}
                for c in AvailableReport.choices
            ],
        })