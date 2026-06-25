import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

const q = (key, fn, interval) =>
  useQuery({ queryKey: key, queryFn: fn, refetchInterval: interval });

export const useOverview = () => q(["overview"], api.overview, 2500);
export const useAIState = () => q(["ai-state"], api.aiState, 2500);
export const useAIHistory = () => q(["ai-history"], api.aiHistory, 2500);
export const useAIModel = () => q(["ai-model"], api.aiModel, 60000);
export const useServices = () => q(["services"], api.services, 3000);
export const useAlerts = () => q(["alerts"], api.alerts, 3000);
export const useRemediation = () => q(["remediation"], api.remediation, 3000);
export const useEscalations = () => q(["escalations"], api.escalations, 3000);
export const useSystem = () => q(["system"], api.system, 5000);
export const useChaosStatus = () => q(["chaos-status"], api.chaosStatus, 2500);
export const useScenarioStatus = () => q(["scenario-status"], api.scenarioStatus, 3000);
export const useLoadStatus = () => q(["load-status"], api.loadStatus, 3000);
export const useSettings = () => q(["settings"], api.settings, 5000);
export const useMetricsRange = (expr, minutes = 15) =>
  q(["range", expr, minutes], () => api.metricsRange(expr, minutes), 5000);
export const useLogs = (service) => q(["logs", service], () => api.logs(service), 4000);
