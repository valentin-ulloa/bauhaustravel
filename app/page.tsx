"use client"

import { Plus, MessageCircle, Plane, Smile, Timer, TrendingUp } from "lucide-react"
import { Button } from "@/components/ui/button"
import { PremiumHeader } from "@/components/premium-header"
import { PremiumStatCard } from "@/components/premium-stat-card"
import { QuickActions } from "@/components/quick-actions"
import { useAgencyStats } from "@/hooks/use-agency-stats"
import { useToast } from "@/components/ui/use-toast"
import { useEffect, useState } from "react"
import { motion } from "framer-motion"

export default function DashboardPage() {
  const [greeting, setGreeting] = useState("Buenos días")

  useEffect(() => {
    const hour = new Date().getHours()
    if (hour >= 5 && hour < 12) {
      setGreeting("Buenos días")
    } else if (hour >= 12 && hour < 18) {
      setGreeting("Buenas tardes")
    } else {
      setGreeting("Buenas noches")
    }
  }, [])

  const { toast } = useToast()

  const { data: stats, isLoading, error, refetch } = useAgencyStats()

  // Debug log para ver qué datos estamos recibiendo
  useEffect(() => {
    if (stats) {
      console.log('📊 Stats loaded:', stats)
    }
  }, [stats])

  useEffect(() => {
    if (error) {
      console.error('❌ Error loading stats:', error)
      toast({
        variant: "destructive",
        title: "Error al cargar las estadísticas",
        description: "No se pudieron cargar los datos. Inténtalo de nuevo.",
        action: (
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Reintentar
          </Button>
        ),
      })
    }
  }, [error, refetch, toast])

  const formatResponseTime = (time: number) => {
    if (time < 60) {
      return (
        new Intl.NumberFormat("es-ES", {
          minimumFractionDigits: 1,
          maximumFractionDigits: 1,
        }).format(time) + " s"
      )
    }
    return (
      new Intl.NumberFormat("es-ES", {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      }).format(time / 60) + " min"
    )
  }

  // Función para formatear satisfacción (backend envía decimal, necesitamos %)
  const formatSatisfactionRate = (rate: number) => {
    return Math.round(rate * 100) + "%"
  }

  const getTrendData = (value: number, type: string) => {
    const trends = {
      total_trips: { trend: "+20% vs mes anterior", direction: "up" as const },
      total_conversations: { trend: "+15% vs mes anterior", direction: "up" as const },
      satisfaction_rate: { trend: "+5% vs mes anterior", direction: "up" as const },
      avg_response_time: { trend: "-10% vs mes anterior", direction: "down" as const },
    }
    return trends[type as keyof typeof trends]
  }

  // Loading state para todo el dashboard
  if (isLoading) {
    return (
      <div className="min-h-screen">
        <PremiumHeader title="Dashboard" />
        <div className="p-4 sm:p-6">
          <div className="animate-pulse space-y-6">
            <div className="h-20 bg-gray-200 rounded-lg"></div>
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-32 bg-gray-200 rounded-lg"></div>
              ))}
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <PremiumHeader title="Dashboard" />

      <div className="p-4 sm:p-6 space-y-6 sm:space-y-8">
        {/* Hero Section */}
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="space-y-4 sm:space-y-6"
        >
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div className="min-w-0 flex-1">
              <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-gray-900 mb-2" aria-live="polite">
                {greeting}, Nagori Travel
              </h1>
              <p className="text-sm sm:text-base lg:text-lg text-gray-600">
                Gestiona tu agencia de viajes con herramientas premium
              </p>
              {/* Debug info - remover en producción */}
              {stats && (
                <p className="text-xs text-blue-600 mt-1">
                  ✅ Conectado con backend - {stats.total_trips} viajes, {stats.total_conversations} conversaciones
                </p>
              )}
            </div>

            <div className="flex flex-col sm:flex-row gap-3 sm:gap-3 flex-shrink-0">
              <Button size="lg" className="btn-primary touch-target">
                <Plus className="w-4 h-4 sm:w-5 sm:h-5 mr-2" />
                <span className="text-sm sm:text-base">Crear Viaje</span>
              </Button>
              <Button variant="outline" size="lg" className="btn-secondary touch-target bg-transparent">
                <MessageCircle className="w-4 h-4 sm:w-5 sm:h-5 mr-2" />
                <span className="text-sm sm:text-base">Ver Conversaciones</span>
              </Button>
            </div>
          </div>
        </motion.section>

        {/* Stats Grid */}
        <section className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 sm:gap-6">
          <PremiumStatCard
            icon={Plane}
            title="Viajes Totales"
            description="Viajes gestionados este mes"
            value={stats?.total_trips || 0}
            trend={getTrendData(stats?.total_trips || 0, "total_trips")?.trend}
            trendDirection={getTrendData(stats?.total_trips || 0, "total_trips")?.direction}
            isLoading={isLoading}
            color="primary"
          />

          <PremiumStatCard
            icon={MessageCircle}
            title="Conversaciones"
            description="Chats activos con clientes"
            value={stats?.total_conversations || 0}
            trend={getTrendData(stats?.total_conversations || 0, "total_conversations")?.trend}
            trendDirection={getTrendData(stats?.total_conversations || 0, "total_conversations")?.direction}
            isLoading={isLoading}
            color="success"
          />

          <PremiumStatCard
            icon={Smile}
            title="Satisfacción"
            description="Puntuación promedio de clientes"
            value={stats?.satisfaction_rate ? formatSatisfactionRate(stats.satisfaction_rate) : "0%"}
            trend={getTrendData(stats?.satisfaction_rate || 0, "satisfaction_rate")?.trend}
            trendDirection={getTrendData(stats?.satisfaction_rate || 0, "satisfaction_rate")?.direction}
            isLoading={isLoading}
            color="warning"
          />

          <PremiumStatCard
            icon={Timer}
            title="Tiempo Respuesta"
            description="Tiempo promedio de respuesta"
            value={stats?.avg_response_time ? formatResponseTime(stats.avg_response_time) : "0 s"}
            trend={getTrendData(stats?.avg_response_time || 0, "avg_response_time")?.trend}
            trendDirection={getTrendData(stats?.avg_response_time || 0, "avg_response_time")?.direction}
            isLoading={isLoading}
            color="error"
          />
        </section>

        {/* Quick Actions */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
          <div className="lg:col-span-1">
            <QuickActions />
          </div>

          <div className="lg:col-span-2">
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.2, duration: 0.4 }}
              className="premium-card p-4 sm:p-6 h-full flex items-center justify-center"
            >
              <div className="text-center">
                <TrendingUp className="h-10 w-10 sm:h-12 sm:w-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-base sm:text-lg font-semibold text-gray-900 mb-2">Gráficos de Rendimiento</h3>
                <p className="text-sm sm:text-base text-gray-600">
                  Los gráficos detallados estarán disponibles en la siguiente fase
                </p>
              </div>
            </motion.div>
          </div>
        </section>
      </div>
    </div>
  )
} 