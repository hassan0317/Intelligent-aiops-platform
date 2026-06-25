import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

export function useAction(fn, msg) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (d) => {
      toast.success(typeof msg === "function" ? msg(d) : msg);
      qc.invalidateQueries();
    },
    onError: (e) => toast.error(e?.message || "action failed"),
  });
}
