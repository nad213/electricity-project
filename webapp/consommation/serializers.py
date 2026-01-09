"""
Serializers for the Consommation API
"""
from rest_framework import serializers


class DateRangeSerializer(serializers.Serializer):
    """Serializer for date range queries"""
    date_debut = serializers.DateField(required=True)
    date_fin = serializers.DateField(required=True)

    def validate(self, data):
        if data['date_debut'] > data['date_fin']:
            raise serializers.ValidationError(
                "La date de début doit être antérieure à la date de fin"
            )
        return data


class SectorSerializer(serializers.Serializer):
    """Serializer for production sector queries"""
    secteur = serializers.CharField(required=True)
    date_debut = serializers.DateField(required=True)
    date_fin = serializers.DateField(required=True)

    def validate(self, data):
        if data['date_debut'] > data['date_fin']:
            raise serializers.ValidationError(
                "La date de début doit être antérieure à la date de fin"
            )
        return data


class CountrySerializer(serializers.Serializer):
    """Serializer for exchanges country queries"""
    pays = serializers.CharField(required=True)
    date_debut = serializers.DateField(required=True)
    date_fin = serializers.DateField(required=True)

    def validate(self, data):
        if data['date_debut'] > data['date_fin']:
            raise serializers.ValidationError(
                "La date de début doit être antérieure à la date de fin"
            )
        return data


class ChartDataSerializer(serializers.Serializer):
    """Serializer for chart data response"""
    data = serializers.ListField()
    layout = serializers.DictField()
    config = serializers.DictField()


class AvailableDatesSerializer(serializers.Serializer):
    """Serializer for available date ranges"""
    min_date = serializers.DateField()
    max_date = serializers.DateField()


class MetadataSerializer(serializers.Serializer):
    """Serializer for metadata (available sectors, countries, etc.)"""
    sectors = serializers.ListField(child=serializers.CharField(), required=False)
    countries = serializers.ListField(child=serializers.CharField(), required=False)
