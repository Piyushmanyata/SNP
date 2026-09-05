export const ROLES = {
  ADMIN: "admin",
  TEAM_LEAD: "team_lead",
  VOLUNTEER: "volunteer",
  CLINICAL_DESK: "clinical_desk_operator",
};

export const ADMIN_ROLES = Object.freeze([ROLES.ADMIN]);
export const DESK_ROLES = Object.freeze([ROLES.ADMIN, ROLES.TEAM_LEAD, ROLES.VOLUNTEER]);
export const CLINICAL_ROLES = Object.freeze([ROLES.ADMIN, ROLES.CLINICAL_DESK]);
export const LEAD_ROLES = Object.freeze([ROLES.ADMIN, ROLES.TEAM_LEAD]);
