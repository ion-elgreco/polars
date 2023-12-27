use crate::dsl::function_expr::{ArrayFunction, FunctionExpr};
use crate::prelude::*;

/// Specialized expressions for [`Series`][Series] of [`DataType::List`][DataType::List].
///
/// [Series]: polars_core::prelude::Series
/// [DataType::List]: polars_core::prelude::DataType::List
pub struct ArrayNameSpace(pub Expr);

impl ArrayNameSpace {
    /// Compute the maximum of the items in every subarray.
    pub fn max(self) -> Expr {
        self.0
            .map_private(FunctionExpr::ArrayExpr(ArrayFunction::Max))
    }

    /// Compute the minimum of the items in every subarray.
    pub fn min(self) -> Expr {
        self.0
            .map_private(FunctionExpr::ArrayExpr(ArrayFunction::Min))
    }

    /// Compute the sum of the items in every subarray.
    pub fn sum(self) -> Expr {
        self.0
            .map_private(FunctionExpr::ArrayExpr(ArrayFunction::Sum))
    }

    /// Compute the std of the items in every subarray.
    pub fn std(self, ddof: u8) -> Expr {
        self.0
            .map_private(FunctionExpr::ArrayExpr(ArrayFunction::Std(ddof)))
    }

    /// Compute the var of the items in every subarray.
    pub fn var(self, ddof: u8) -> Expr {
        self.0
            .map_private(FunctionExpr::ArrayExpr(ArrayFunction::Var(ddof)))
    }

    /// Compute the median of the items in every subarray.
    pub fn median(self) -> Expr {
        self.0
            .map_private(FunctionExpr::ArrayExpr(ArrayFunction::Median))
    }

    /// Keep only the unique values in every sub-array.
    pub fn unique(self) -> Expr {
        self.0
            .map_private(FunctionExpr::ArrayExpr(ArrayFunction::Unique(false)))
    }

    /// Keep only the unique values in every sub-array.
    pub fn unique_stable(self) -> Expr {
        self.0
            .map_private(FunctionExpr::ArrayExpr(ArrayFunction::Unique(true)))
    }

    /// Cast the Array column to List column with the same inner data type.
    pub fn to_list(self) -> Expr {
        self.0
            .map_private(FunctionExpr::ArrayExpr(ArrayFunction::ToList))
    }

    #[cfg(feature = "array_any_all")]
    /// Evaluate whether all boolean values are true for every subarray.
    pub fn all(self) -> Expr {
        self.0
            .map_private(FunctionExpr::ArrayExpr(ArrayFunction::All))
    }

    #[cfg(feature = "array_any_all")]
    /// Evaluate whether any boolean value is true for every subarray
    pub fn any(self) -> Expr {
        self.0
            .map_private(FunctionExpr::ArrayExpr(ArrayFunction::Any))
    }
}
